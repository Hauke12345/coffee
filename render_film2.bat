@echo off
rem Morning coffee v2 - full-quality render on an NVIDIA GPU (Windows). Run from this folder.
rem One continuous take (266 frames, 11.1 s): the camera glides between the framings instead of cutting.
rem One-time setup (Python 3.13 from python.org):
rem   py -3.13 -m pip install bpy==5.2.2 numpy scipy scikit-image imageio-ffmpeg
set CANDLE_GPU=1
set RES_X=1920
set RES_Y=1080
set SPP=256
rem skip frames that already exist, so an interrupted render can be resumed
set RESUME=1
py -3.13 scene2.py film %RES_X% %RES_Y% %SPP% frames || goto :err
py -3.13 make_film2.py frames coffee_film_v2.mp4 || goto :err
echo Done: coffee_film_v2.mp4
goto :eof
:err
echo Something failed - see the messages above.
