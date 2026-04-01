import os

initial_text = 'CASES_PER_CATEGORY = 100'
final_text = initial_text.replace('100', '50')
with open('../full_name.txt', 'r') as r1:
    full_names = [x.strip() for x in r1.readlines()]

# cnt = 0
for full_name in full_names:
    with open(f'repo/{full_name}/start.py', 'r') as r1:
        text = r1.read()
    
    with open(f'repo/{full_name}/start.py', 'w') as w1:
        w1.write(text.replace(initial_text, final_text))
    # if initial_text in text:
    #     cnt += 1

# print(cnt)