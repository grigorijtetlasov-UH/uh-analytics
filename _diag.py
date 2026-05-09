import pandas as pd, glob
files = sorted(glob.glob('data/crm/daily/*.xlsx'))
print(f'Файлів: {len(files)}')
dfs = []
for f in files:
    try:
        d = pd.read_excel(f)
        dfs.append(d)
    except Exception as e:
        print(f'ERR {f}: {e}')
big = pd.concat(dfs, ignore_index=True)
print(f'Всього рядків після concat: {len(big)}')
date_col = 'Дата'
print(f'Тип колонки {date_col}: {big[date_col].dtype}')
parsed = pd.to_datetime(big[date_col], errors='coerce')
big['_d'] = parsed.dt.strftime('%Y-%m-%d')
print()
print('Розподіл по днях (тail 10):')
print(big['_d'].value_counts().sort_index().tail(10).to_string())
print()
print('NaT:', big['_d'].isna().sum())
