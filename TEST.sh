python3 scripts/batch.py --vehN-list 50,60,70,80 --pstep 0.1 --seeds 1 --outcsv out/TEST.csv
python3 DataVisualization.py --csv out/TEST.csv
echo "[OK] 检验产物：./out/TEST.csv、./graph/*"
