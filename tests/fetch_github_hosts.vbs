' ================================
' GitHub Hosts Updater (VBS Version - Silent Mode)
' ================================

Option Explicit

Dim shell, fso, tempFile, hostsFile, remoteUrl
Dim newContent, skip, line, lines, success

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

tempFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\hosts_temp_" & Rnd(1000) & ".txt"
hostsFile = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\drivers\etc\hosts"
remoteUrl = "https://raw.hellogithub.com/hosts"

' Check admin privileges
If Not IsAdmin() Then
    RunAsAdmin()
    WScript.Quit
End If

On Error Resume Next

' Step 1: Read hosts file and remove old records
newContent = ""
skip = False

If fso.FileExists(hostsFile) Then
    Set lines = fso.OpenTextFile(hostsFile, 1, False)
    Do Until lines.AtEndOfStream
        line = lines.ReadLine
        If line = "# GitHub520 Host Start" Then
            skip = True
        ElseIf line = "# Github520 Host End" Then
            skip = False
        ElseIf Not skip Then
            newContent = newContent & line & vbCrLf
        End If
    Loop
    lines.Close
End If

' Save cleaned content to temp file
Set lines = fso.CreateTextFile(tempFile, True)
lines.Write newContent
lines.Close

' Step 2: Download latest GitHub Hosts
success = DownloadFile(remoteUrl, tempFile, True)

If Not success Then
    If fso.FileExists(tempFile) Then fso.DeleteFile tempFile, True
    WScript.Quit 1
End If

' Step 3: Update hosts file
fso.CopyFile tempFile, hostsFile, True

' Clean up temp file
If fso.FileExists(tempFile) Then fso.DeleteFile tempFile, True

If Err.Number <> 0 Then
    shell.Popup "Error: " & Err.Description, 3, "GitHub Hosts", vbCritical
Else
    shell.Popup "Hosts file updated successfully!", 1, "GitHub Hosts", vbInformation
End If

WScript.Quit 0

' ================================
' 函数: 检查是否为管理员
' ================================
Function IsAdmin()
    Dim objNet
    On Error Resume Next
    Set objNet = CreateObject("Schedule.Service")
    objNet.Connect
    IsAdmin = (Err.Number = 0)
    On Error GoTo 0
End Function

' ================================
' 函数: 以管理员身份重新运行
' ================================
Sub RunAsAdmin()
    Dim objShell, objFSO, strPath, strArgs
    Set objShell = CreateObject("Shell.Application")
    strPath = WScript.ScriptFullName
    objShell.ShellExecute "wscript.exe", Chr(34) & strPath & Chr(34), "", "runas", 0
End Sub

' ================================
' 函数: 下载文件
' ================================
Function DownloadFile(url, filePath, append)
    Dim objXMLHTTP, objADOStream, objFSO, objFile
    
    DownloadFile = False
    
    On Error Resume Next
    
    ' 使用 XMLHTTP 下载
    Set objXMLHTTP = CreateObject("MSXML2.XMLHTTP.3.0")
    objXMLHTTP.Open "GET", url, False
    objXMLHTTP.Send
    
    If objXMLHTTP.Status = 200 Then
        ' 追加到文件
        Set objFSO = CreateObject("Scripting.FileSystemObject")
        Set objFile = objFSO.OpenTextFile(filePath, 8, True)
        objFile.Write objXMLHTTP.ResponseText
        objFile.Close
        DownloadFile = True
    End If
    
    On Error GoTo 0
End Function
