package org.mamoru.omnichat.client.tts;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.stream.Stream;

/** Manual check on a copy of the real glados model; enable with env MODELREPAIR_MANUAL=true. */
@EnabledIfEnvironmentVariable(named = "MODELREPAIR_MANUAL", matches = "true")
class ModelRepairManualTest {
    @Test
    void gladosCopy() throws IOException {
        Path src = Path.of("run/config/omnichat/models/glados").toAbsolutePath();
        Path tmp = Files.createTempDirectory("glados-copy");
        try (Stream<Path> s = Files.walk(src)) {
            for (Path p : (Iterable<Path>) s::iterator) {
                Path t = tmp.resolve(src.relativize(p).toString());
                if (Files.isDirectory(p)) Files.createDirectories(t);
                else Files.copy(p, t);
            }
        }
        try {
            ModelRepair.Health before = ModelRepair.check(tmp);
            System.out.println("MANUAL before: " + before.status() + " suggested=" + before.suggestedVoice()
                    + " voices=" + before.voices().size() + " problem=" + before.problem());
            ModelRepair.apply(tmp, before.suggestedVoice());
            System.out.println("MANUAL after: " + ModelRepair.check(tmp));
            System.out.println("MANUAL bak exists: " + Files.exists(tmp.resolve("glados.onnx.bak")));
        } finally {
            try (Stream<Path> s = Files.walk(tmp)) {
                s.sorted(Comparator.reverseOrder()).forEach(p -> p.toFile().delete());
            }
        }
    }
}
