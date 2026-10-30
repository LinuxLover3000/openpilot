#!/usr/bin/env bash

# Sets up a virtual display for running map renderer and simulator without an X11 display

if uname -r | grep -q "WSL2"; then
  DISP_ID=0 # WSLg uses display :0
else
  DISP_ID=99 # Standard Xvfb display
fi
export DISPLAY=:$DISP_ID

if ! command -v Xvfb >/dev/null; then
  echo "Xvfb is required. Install it with: sudo apt-get install xvfb"
  return 1 2>/dev/null || exit 1
fi

# Authenticate before backgrounding so sudo never stops while trying to read
# from the terminal.
if ! sudo -v; then
  return 1 2>/dev/null || exit 1
fi

sudo Xvfb "$DISPLAY" -screen 0 2160x1080x24 >/tmp/openpilot-xvfb.log 2>&1 &
xvfb_pid=$!

# check for x11 socket for the specified display ID
for _ in {1..30}; do
  if [ -S "/tmp/.X11-unix/X$DISP_ID" ]; then
    touch ~/.Xauthority
    export XDG_SESSION_TYPE="x11"
    return 0 2>/dev/null || exit 0
  fi

  if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "Xvfb failed to start:"
    cat /tmp/openpilot-xvfb.log
    return 1 2>/dev/null || exit 1
  fi

  echo "Waiting for Xvfb..."
  sleep 1
done

echo "Timed out waiting for Xvfb. See /tmp/openpilot-xvfb.log"
return 1 2>/dev/null || exit 1