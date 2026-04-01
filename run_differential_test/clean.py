import os

root_path = '/data00/rdhu/ase26/final_differential_test/repo_new'
authors = [os.path.join(root_path, x) for x in os.listdir(root_path)]
# full_name = list()

with open('/data00/rdhu/ase26/final_final_repo.txt', 'r') as r1:
    full_names = [x.strip() for x in r1.readlines()]

# for author in authors:
#     full_name.extend([os.path.join(author, x) for x in os.listdir(author)])

# print(len(full_name))
os.system('mkdir -p /data00/rdhu/ase26/run_differential_test/repo')

for full_name in full_names:
    os.system(f'mkdir -p /data00/rdhu/ase26/run_differential_test/repo/{full_name}')
    os.system(f'cp {root_path}/{full_name}/start.py /data00/rdhu/ase26/run_differential_test/repo/{full_name}')