' ================================
' GitHub Hosts 更新工具 (VBS版本)
' ================================

Option Explicit

Dim shell, fso, tempFile, hostsFile, remoteUrl, objHTTP, objStream
Dim content, newContent, skip, line, lines, success

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

tempFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\hosts_temp_" & Rnd(1000) & ".txt"
hostsFile = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\drivers\etc\hosts"
remoteUrl = "https://raw.hellogithub.com/hosts"

' 检查管理员权限
If Not IsAdmin() Then
    RunAsAdmin()
    WScript.Quit
End If

WScript.Echo "==============================" & vbCrLf & _
             "GitHub Hosts 更新工具" & vbCrLf & _
             "==============================" & vbCrLf & vbCrLf & _
             "开始更新 hosts 文件..."

On Error Resume Next

' 步骤1: 读取 hosts 文件并清理旧记录
WScript.Echo "[1/3] 正在清理旧的 GitHub520 记录..."
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
Else
    WScript.Echo "警告: hosts 文件不存在，将创建新文件"
End If

' 保存清理后的内容到临时文件
Set lines = fso.CreateTextFile(tempFile, True)
lines.Write newContent
lines.Close

' 步骤2: 下载最新的 GitHub Hosts
WScript.Echo "[2/3] 正在下载最新的 GitHub Hosts..."
success = DownloadFile(remoteUrl, tempFile, True)

If Not success Then
    WScript.Echo "错误: 下载失败，请检查网络连接"
    fso.DeleteFile tempFile, True
    WScript.Quit 1
End If

' 步骤3: 更新 hosts 文件
WScript.Echo "[3/3] 正在更新 hosts 文件..."
fso.CopyFile tempFile, hostsFile, True

' 清理临时文件
fso.DeleteFile tempFile, True

If Err.Number <> 0 Then
    WScript.Echo "错误: " & Err.Description
    WScript.Quit 1
End If

WScript.Echo vbCrLf & "==============================" & vbCrLf & _
             "✓ Hosts 文件更新完成！" & vbCrLf & _
             "=============================="
WScript.Sleep 2000

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
