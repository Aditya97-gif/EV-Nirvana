# VAHAN Manual Export Procedure

## Why manual?
The VAHAN dashboard (vahan.parivahan.gov.in) does not expose a public API. Automated export is not feasible without login credentials.

## Steps
1. Go to https://vahan.parivahan.gov.in/vahan4dashboard
2. Log in with your credentials (if required).
3. Under **Reports > Vehicle Registration**, select:
   - State: Maharashtra (or your configured state)
   - Year: 2019 onwards (one file per year is fine)
   - Fuel Type: **Electric** and **Battery Operated Vehicle (BOV)**
   - Group By: RTO + Month + Vehicle Class
4. Export as **CSV** or **XLSX**.
5. Place the file(s) in `data/raw/vahan/` — the pipeline will auto-detect them.

## Expected columns
`State, RTO_Code, RTO_Name, Year, Month, Fuel, Vehicle_Class, Count`

## Note
If you have secondary/aggregated datasets (e.g. Kaggle), place them here too — they will be tagged `source=secondary`.
