chcp 65001
color 37
@echo off
cls
echo =====================================
echo Bootstraper HIXOS
echo By Kraits
echo ■■■
echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
echo =====================================
echo Bootstraper HIXOS
echo By Kraits
echo ■■■■■■
echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
echo =====================================
echo Bootstraper HIXOS
echo By Kraits
echo ■■■■■■■■■■■
echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
echo =====================================
echo Bootstraper HIXOS
echo By Kraits
echo ■■■■■■■■■■■■■■■■■■■■■■■
echo =====================================
ping -n 2 127.0.0.1 > NUL 
cls
echo =====================================
echo Installing modules - Wait
echo =====================================
cd system
cd modules
python.exe -m pip install --upgrade pip
pip3 install -r Modules.txt
cd ..
cd ..
cls
echo =====================================
echo Installing modules - Done
echo =====================================
ping -n 3 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■■■■■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■■■■■■■■■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■■■■■■■■■■■■■■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
Echo =====================================
Echo Checking files - Wait
Echo ■■■■■■■■■■■■■■■■■■■■■■■
Echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
echo =====================================
Echo Checking files - Done
echo =====================================
ping -n 2 127.0.0.1 > NUL
cls
cd system
cls
python HIXOS.py