"""
speech_input.py - Simple voice question capture helpers.

Desktop support currently uses the built-in Windows speech recognizer
through PowerShell and System.Speech, so no external cloud STT setup is
required for the desktop GUI on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap


def capture_speech_text(timeout_sec: int = 6) -> str:
    if os.name != "nt":
        raise RuntimeError("Desktop voice input is currently implemented for Windows only.")

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise RuntimeError("PowerShell was not found, so microphone speech capture is unavailable.")

    timeout_sec = max(3, int(timeout_sec))
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        Add-Type -AssemblyName System.Speech
        $culture = [System.Globalization.CultureInfo]::CurrentUICulture
        $recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture)
        $grammar = New-Object System.Speech.Recognition.DictationGrammar
        $recognizer.LoadGrammar($grammar)
        $recognizer.SetInputToDefaultAudioDevice()
        $result = $recognizer.Recognize([TimeSpan]::FromSeconds({timeout_sec}))
        if ($null -eq $result -or [string]::IsNullOrWhiteSpace($result.Text)) {{
            Write-Error 'No speech was detected. Please try again.'
            exit 2
        }}
        Write-Output $result.Text.Trim()
        """
    ).strip()

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        [powershell, "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout_sec + 10,
        creationflags=creationflags,
    )

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "Speech recognition failed.").strip()
        raise RuntimeError(message)

    transcript = (proc.stdout or "").strip()
    if not transcript:
        raise RuntimeError("No speech was detected. Please try again.")
    return transcript
