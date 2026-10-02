package org.mamoru.omnichat.client.tts;

import com.k2fsa.sherpa.onnx.LibraryLoader;
import com.sun.jna.Library;
import com.sun.jna.Native;
import com.sun.jna.WString;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Extracts the bundled sherpa-onnx / onnxruntime natives into a stable, content-addressed
 * directory ({@code config/omnichat/natives/win-x64-<hash>/}) and loads them exactly once per JVM.
 * <p>
 * The directory name is derived from the SHA-256 of all bundled DLLs, so a mod update with new
 * natives gets a fresh directory while unchanged natives are reused across launches without
 * rewriting. Existing files are verified (size + SHA-256) and never overwritten when identical,
 * so a second game instance that already has them loaded (and therefore locked) is not disturbed.
 */
final class SherpaNatives {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    private static final String RESOURCE_DIR = "/natives/win-x64/";
    private static final String PLATFORM = "win-x64";
    /** Prefix of the per-launch temp dirs created by older builds in java.io.tmpdir. */
    private static final String LEGACY_TEMP_PREFIX = "omnichat-natives";
    /** Load order matters: dependencies first. */
    private static final String[] NATIVE_LIBS = {
            "onnxruntime.dll",
            "onnxruntime_providers_shared.dll",
            "cargs.dll",
            "sherpa-onnx-c-api.dll",
            "sherpa-onnx-cxx-api.dll",
            "sherpa-onnx-jni.dll"
    };

    private static boolean loaded;

    private SherpaNatives() {
    }

    static synchronized void ensureLoaded() {
        if (loaded) {
            return;
        }

        // Only win-x64 natives are bundled. Check before touching anything native,
        // so Kernel32 (Native.load("kernel32")) is never initialized on other platforms.
        String osName = System.getProperty("os.name", "unknown");
        String osArch = System.getProperty("os.arch", "unknown");
        if (!isWindowsX64(osName, osArch)) {
            throw new IllegalStateException("sherpa-onnx TTS is only bundled for Windows x64 (this is "
                    + osName + "/" + osArch + ")");
        }

        // Disable sherpa-onnx's own auto-loading; we handle it ourselves
        LibraryLoader.setAutoLoadEnabled(false);

        Map<String, byte[]> bundled = readBundledLibraries();
        Map<String, byte[]> digests = new LinkedHashMap<>();
        for (Map.Entry<String, byte[]> e : bundled.entrySet()) {
            digests.put(e.getKey(), sha256(e.getValue()));
        }

        Path nativesRoot = OmnichatConfig.getConfigDir().resolve("natives");
        Path dir = nativesRoot.resolve(PLATFORM + "-" + combinedHash(digests));
        try {
            Files.createDirectories(dir);
        } catch (IOException e) {
            throw new RuntimeException("Failed to create natives directory: " + dir, e);
        }

        int written = 0;
        for (String libName : NATIVE_LIBS) {
            if (ensureFile(dir, libName, bundled.get(libName), digests.get(libName))) {
                written++;
            }
        }
        bundled.clear();
        LOGGER.info("sherpa-onnx natives at {} ({} extracted, {} reused)", dir, written, NATIVE_LIBS.length - written);

        try {
            // Process-global; set once so Windows can resolve dependent DLLs from our directory.
            // Wide-char variant: the path may contain non-ASCII characters (user profile name).
            if (!Kernel32.INSTANCE.SetDllDirectoryW(new WString(dir.toAbsolutePath().toString()))) {
                LOGGER.warn("SetDllDirectoryW failed for {}", dir);
            }

            // The JDK de-duplicates System.load by absolute path; the path is stable now,
            // so a retry after a partial failure cannot load a second copy of a module.
            for (String libName : NATIVE_LIBS) {
                System.load(dir.resolve(libName).toAbsolutePath().toString());
                LOGGER.debug("Loaded native library: {}", libName);
            }
        } catch (LinkageError e) {
            throw new RuntimeException("Failed to load sherpa-onnx native libraries", e);
        }

        loaded = true;

        // Best-effort housekeeping after a successful load; never fails the caller.
        cleanupStaleVersions(nativesRoot, dir);
        cleanupLegacyTempDirs();
    }

    static boolean isWindowsX64(String osName, String osArch) {
        String os = osName.toLowerCase(Locale.ROOT);
        String arch = osArch.toLowerCase(Locale.ROOT);
        return os.startsWith("windows") && (arch.equals("amd64") || arch.equals("x86_64"));
    }

    private static Map<String, byte[]> readBundledLibraries() {
        Map<String, byte[]> result = new LinkedHashMap<>();
        for (String libName : NATIVE_LIBS) {
            String resourcePath = RESOURCE_DIR + libName;
            try (InputStream is = SherpaNatives.class.getResourceAsStream(resourcePath)) {
                if (is == null) {
                    throw new RuntimeException("Native library not found in resources: " + resourcePath);
                }
                result.put(libName, is.readAllBytes());
            } catch (IOException e) {
                throw new RuntimeException("Failed to read bundled native library: " + libName, e);
            }
        }
        return result;
    }

    /**
     * Makes sure {@code dir/libName} has exactly {@code content}.
     *
     * @return true if the file was (re)written, false if an identical file was reused
     */
    private static boolean ensureFile(Path dir, String libName, byte[] content, byte[] digest) {
        Path target = dir.resolve(libName);
        if (matches(target, content.length, digest)) {
            return false;
        }

        // Write to a unique temp file in the same directory, then move into place, so a crash or a
        // concurrently starting instance never sees (or loads) a half-written DLL.
        Path tmp = null;
        try {
            tmp = Files.createTempFile(dir, libName + ".", ".tmp");
            Files.write(tmp, content);
            try {
                Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
            } catch (IOException moveFailed) {
                // Typically: another instance extracted it concurrently and already has it loaded
                // (locked). Fine as long as what's there now is identical.
                if (!matches(target, content.length, digest)) {
                    throw moveFailed;
                }
                return false;
            }
            return true;
        } catch (IOException e) {
            throw new RuntimeException("Failed to extract native library " + libName + " to " + dir
                    + " (is it locked by another process?)", e);
        } finally {
            if (tmp != null) {
                try {
                    Files.deleteIfExists(tmp);
                } catch (IOException ignored) {
                    // leftover *.tmp is removed on a later launch's cleanup
                }
            }
        }
    }

    private static boolean matches(Path file, long size, byte[] digest) {
        try {
            if (!Files.isRegularFile(file) || Files.size(file) != size) {
                return false;
            }
            return Arrays.equals(sha256(Files.readAllBytes(file)), digest);
        } catch (IOException e) {
            return false;
        }
    }

    /** Removes other version directories under {@code nativesRoot}; locked ones are skipped. */
    private static void cleanupStaleVersions(Path nativesRoot, Path current) {
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(nativesRoot)) {
            for (Path p : stream) {
                if (!p.equals(current) && Files.isDirectory(p)) {
                    deleteRecursively(p);
                }
            }
        } catch (IOException e) {
            LOGGER.debug("Could not scan {} for stale natives", nativesRoot, e);
        }
        // Leftover temp files from an interrupted extraction in the current directory.
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(current, "*.tmp")) {
            for (Path p : stream) {
                Files.deleteIfExists(p);
            }
        } catch (IOException e) {
            LOGGER.debug("Could not clean temp files in {}", current, e);
        }
    }

    /** Older builds extracted into a fresh {@code %TEMP%/omnichat-natives*} dir on every load and never cleaned up. */
    private static void cleanupLegacyTempDirs() {
        String tmp = System.getProperty("java.io.tmpdir");
        if (tmp == null || tmp.isBlank()) {
            return;
        }
        Path tmpDir = Path.of(tmp);
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(tmpDir, LEGACY_TEMP_PREFIX + "*")) {
            int removed = 0;
            for (Path p : stream) {
                if (Files.isDirectory(p) && deleteRecursively(p)) {
                    removed++;
                }
            }
            if (removed > 0) {
                LOGGER.info("Removed {} legacy native temp dir(s) from {}", removed, tmpDir);
            }
        } catch (IOException e) {
            LOGGER.debug("Could not scan {} for legacy native temp dirs", tmpDir, e);
        }
    }

    /**
     * Deletes a directory tree, skipping files that can't be deleted (e.g. DLLs still loaded by
     * another running game instance).
     *
     * @return true if the directory itself is gone
     */
    private static boolean deleteRecursively(Path root) {
        try (Stream<Path> walk = Files.walk(root)) {
            walk.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                    // locked or not empty — leave it for a later launch
                }
            });
        } catch (IOException | RuntimeException e) {
            LOGGER.debug("Could not fully delete {}", root, e);
        }
        return !Files.exists(root);
    }

    private static String combinedHash(Map<String, byte[]> digests) {
        MessageDigest md = newSha256();
        for (Map.Entry<String, byte[]> e : digests.entrySet()) {
            md.update(e.getKey().getBytes(java.nio.charset.StandardCharsets.UTF_8));
            md.update((byte) 0);
            md.update(e.getValue());
        }
        return HexFormat.of().formatHex(md.digest(), 0, 8);
    }

    private static byte[] sha256(byte[] data) {
        return newSha256().digest(data);
    }

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }

    private interface Kernel32 extends Library {
        Kernel32 INSTANCE = Native.load("kernel32", Kernel32.class);

        boolean SetDllDirectoryW(WString lpPathName);
    }
}
