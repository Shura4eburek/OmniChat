# Helpers for scripts/smoke.sh: tell dev Minecraft processes apart by command line
# (all of them are java.exe, which um's WinDrive can't distinguish).
#   mcproc.ps1 pid   <regex>   -> PID of the java.exe whose command line matches
#   mcproc.ps1 hwnd  <pid>     -> main window handle of that process
#   mcproc.ps1 focus <pid>     -> bring its window to the foreground
#   mcproc.ps1 kill  <regex>   -> kill every matching java.exe
param([Parameter(Mandatory = $true)][string]$Cmd, [Parameter(Mandatory = $true)][string]$Arg)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Fg {
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern void keybd_event(byte vk, byte scan, uint flags, IntPtr extra);
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool AttachThreadInput(uint a, uint b, bool attach);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    // same trick as um's WinDrive, but for an exact window: returns true only if THIS window is foreground
    public static bool Focus(IntPtr h) {
        if (GetForegroundWindow() == h) return true;
        keybd_event(0x12, 0, 0, IntPtr.Zero);               // a lone Alt press lifts the foreground lock
        keybd_event(0x12, 0, 2, IntPtr.Zero);
        uint dummy, target = GetWindowThreadProcessId(h, out dummy), me = GetCurrentThreadId();
        AttachThreadInput(me, target, true);
        ShowWindow(h, 9);                                   // SW_RESTORE
        SetForegroundWindow(h);
        AttachThreadInput(me, target, false);
        System.Threading.Thread.Sleep(300);
        return GetForegroundWindow() == h;
    }
}
"@

function Find($regex) {
    Get-CimInstance Win32_Process -Filter "Name='java.exe'" | Where-Object { $_.CommandLine -match $regex }
}

switch ($Cmd) {
    "pid"   { (Find $Arg | Select-Object -First 1).ProcessId }
    "hwnd"  { [int64](Get-Process -Id ([int]$Arg)).MainWindowHandle }
    "focus" { [Fg]::Focus((Get-Process -Id ([int]$Arg)).MainWindowHandle) }
    "kill"  { Find $Arg | ForEach-Object { Stop-Process -Id $_.ProcessId -Force } }
}
