if command -v gnome-terminal &> /dev/null; then
    TERMINAL="gnome-terminal --"
elif command -v xterm &> /dev/null; then
    TERMINAL="xterm -hold -e"
elif command -v konsole &> /dev/null; then
    TERMINAL="konsole --separate --noclose -e"
elif command -v wsl.exe &> /dev/null; then
    TERMINAL="wsl.exe -d Ubuntu-24.04 -e bash -c \"echo 'Test terminal window'; read\""
else
    echo "No supported terminal emulator found"
    exit 1
fi

echo "Using terminal: $TERMINAL"
$TERMINAL bash -c "echo 'Test terminal window'; read"