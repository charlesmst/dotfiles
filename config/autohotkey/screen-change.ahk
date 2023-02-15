
dcputil(display, value){
        Run "D:/ScreenServer/winddcutil.exe" setvcp %display%  60 0x%value%
}

selectDisplayPc(){
        dcputil(1, "11")
}
selectDisplayMac(){

        dcputil(1, "0f")
}
F14::selectDisplayPc()
F15::selectDisplayMac()
