Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile("D:\AiTranslator\tests\speech_en.wav")
$s.Speak("Hello, this is a test video for the translator.")
$s.Dispose()
Get-Item "D:\AiTranslator\tests\speech_en.wav" | Select-Object Name, Length
