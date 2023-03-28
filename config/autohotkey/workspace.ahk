; AutoHotkey v1 script

; Get hwnd of AutoHotkey window, for listener

; Path to the DLL, relative to the script
VDA_PATH := "C:\VirtualDesktopAccessor.dll"
hVirtualDesktopAccessor := DllCall("LoadLibrary", "Str", VDA_PATH, "Ptr")

GetDesktopCountProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "GetDesktopCount", "Ptr")
GoToDesktopNumberProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "GoToDesktopNumber", "Ptr")
GetCurrentDesktopNumberProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "GetCurrentDesktopNumber", "Ptr")
IsWindowOnCurrentVirtualDesktopProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "IsWindowOnCurrentVirtualDesktop", "Ptr")
IsWindowOnDesktopNumberProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "IsWindowOnDesktopNumber", "Ptr")
MoveWindowToDesktopNumberProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "MoveWindowToDesktopNumber", "Ptr")
IsPinnedWindowProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "IsPinnedWindow", "Ptr")
GetDesktopNameProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "GetDesktopName", "Ptr")
SetDesktopNameProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "SetDesktopName", "Ptr")
CreateDesktopProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "CreateDesktop", "Ptr")
RemoveDesktopProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "RemoveDesktop", "Ptr")

; On change listeners
RegisterPostMessageHookProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "RegisterPostMessageHook", "Ptr")
UnregisterPostMessageHookProc := DllCall("GetProcAddress", "Ptr", hVirtualDesktopAccessor, "AStr", "UnregisterPostMessageHook", "Ptr")

GetDesktopCount() {
    global GetDesktopCountProc
    count := DllCall(GetDesktopCountProc, "Int")
    return count
}

MoveCurrentWindowToDesktop(desktopNumber) {
    global MoveWindowToDesktopNumberProc, GoToDesktopNumberProc
    WinGet, activeHwnd, ID, A
    DllCall(MoveWindowToDesktopNumberProc, "Ptr", activeHwnd, "Int", desktopNumber, "Int")
    DllCall(GoToDesktopNumberProc, "Int", desktopNumber)
}

GoToPrevDesktop() {
    global GetCurrentDesktopNumberProc, GoToDesktopNumberProc
    current := DllCall(GetCurrentDesktopNumberProc, "Int")
    last_desktop := GetDesktopCount() - 1
    ; If current desktop is 0, go to last desktop
    if (current = 0) {
        MoveOrGotoDesktopNumber(last_desktop)
    } else {
        MoveOrGotoDesktopNumber(current - 1)
    }
    return
}

GoToNextDesktop() {
    global GetCurrentDesktopNumberProc
    current := DllCall(GetCurrentDesktopNumberProc, "Int")
    last_desktop := GetDesktopCount() - 1
    ; If current desktop is last, go to first desktop
    if (current = last_desktop) {
        MoveOrGotoDesktopNumber(0)
    } else {
        MoveOrGotoDesktopNumber(current + 1)
    }
    return
}

GoToDesktopNumber(num) {
    global GoToDesktopNumberProc
    DllCall(GoToDesktopNumberProc, "Int", num, "Int")
    return
}
MoveOrGotoDesktopNumber(num) {
    ; If user is holding down Mouse left button, move the current window also
    if (GetKeyState("LButton")) {
        MoveCurrentWindowToDesktop(num)
    } else {

        global GetCurrentDesktopNumberProc, GoToDesktopNumberProc
        CurrentDesktop := DllCall(GetCurrentDesktopNumberProc, "Int")
        if(CurrentDesktop == num){
            return
        }
        if (CurrentDesktop < num){
            GoToDesktopNumber(num - 1)
            Send ^#{Right}
        }else{
            GoToDesktopNumber(num + 1)
            Send ^#{Left}
        }
    }
    return
}

MoveToDesktopNumber(num) {
    MoveCurrentWindowToDesktop(num)
    return
}
GetDesktopName(num) {
    global GetDesktopNameProc
    utf8_buffer := ""
    utf8_buffer_len := VarSetCapacity(utf8_buffer, 1024, 0)
    ran := DllCall(GetDesktopNameProc, "Int", num, "Ptr", &utf8_buffer, "Ptr", utf8_buffer_len, "Int")
    name := StrGet(&utf8_buffer, 1024, "UTF-8")
    return name
}
SetDesktopName(num, name) {
    ; NOTICE! For UTF-8 to work AHK file must be saved with UTF-8 with BOM

    global SetDesktopNameProc
    VarSetCapacity(name_utf8, 1024, 0)
    StrPut(name, &name_utf8, "UTF-8")
    ran := DllCall(SetDesktopNameProc, "Int", num, "Ptr", &name_utf8, "Int")
    return ran
}
CreateDesktop() {
    global CreateDesktopProc
    ran := DllCall(CreateDesktopProc)
    return ran
}
RemoveDesktop(remove_desktop_number, fallback_desktop_number) {
    global RemoveDesktopProc
    ran := DllCall(RemoveDesktopProc, "Int", remove_desktop_number, "Int", fallback_desktop_number, "Int")
    return ran
}

SetDesktopName(0, "Browser")
SetDesktopName(3, "Terminal")

; How to listen to desktop changes
DllCall(RegisterPostMessageHookProc, "Ptr", A_ScriptHwnd, "Int", 0x1400 + 30, "Int")
OnMessage(0x1400 + 30, "OnChangeDesktop")
OnChangeDesktop(wParam, lParam, msg, hwnd) {
    Critical, 100
    OldDesktop := wParam + 1
    NewDesktop := lParam + 1
    Name := GetDesktopName(NewDesktop - 1)

    ; Use Dbgview.exe to checkout the output debug logs
    OutputDebug % "Desktop changed to " Name " from " OldDesktop " to " NewDesktop
}


^!+1:: MoveToDesktopNumber(0)
^!+2:: MoveToDesktopNumber(1)
^!+3:: MoveToDesktopNumber(2)
^!+4:: MoveToDesktopNumber(3)
^!+5:: MoveToDesktopNumber(4)
^!+6:: MoveToDesktopNumber(5)
^!+7:: MoveToDesktopNumber(6)
^!+8:: MoveToDesktopNumber(7)
^!+9:: MoveToDesktopNumber(8)

!+1:: MoveOrGotoDesktopNumber(0)
!+2:: MoveOrGotoDesktopNumber(1)
!+3:: MoveOrGotoDesktopNumber(2)
!+4:: MoveOrGotoDesktopNumber(3)
!+5:: MoveOrGotoDesktopNumber(4)
!+6:: MoveOrGotoDesktopNumber(5)
!+7:: MoveOrGotoDesktopNumber(6)
!+8:: MoveOrGotoDesktopNumber(7)
; !+9:: MoveOrGotoDesktopNumber(8)


Test(){
    DetectHiddenWindows, On

    WinGet, id, List,,, Program Manager
    Loop %id%
    {
            this_id := id%A_Index%
            WinGetTitle, title, ahk_id %this_id%
            If (title = "")
                    continue
            WinGet, Style, Style, ahk_id %this_id%
            if !(Style & 0x10000000)	; WS_VISIBLE
                    continue
            wins .= title ? title "`n" : ""

            WinGet, activeHwnd, ID, ahk_id %this_id%
            test:= DllCall(IsWindowOnCurrentVirtualDesktopProc, "Ptr", activeHwnd, "Int")
            wins .= test

            OutputDebug % "Test  " test 
    }
    MsgBox, %wins%
}

!+9:: Test()




; focus window asking for attention
; Register shell hook to detect flashing windows.
DllCall("RegisterShellHookWindow", "Ptr",A_ScriptHwnd)
OnMessage(DllCall("RegisterWindowMessage", "Str","SHELLHOOK"), "ShellEvent")
;...

ShellEvent(wParam, lParam) {
    If (wParam = 0x8006) ; HSHELL_FLASH
    {   ; lParam contains the ID of the window which flashed:
        WinActivate, ahk_id %lParam%
    }
}
