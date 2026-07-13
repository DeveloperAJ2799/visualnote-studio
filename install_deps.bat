@echo off
cd /d D:\tagmango\remotion_project
echo Installing Three.js dependencies...
npm install three @react-three/fiber @remotion/three @react-three/drei
echo Installing dev dependencies...
npm install -D @types/three
echo Done!
