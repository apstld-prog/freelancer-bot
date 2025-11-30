import requests

url = 'https://www.peopleperhour.com/search/projects'
params = {'keyword': 'ebook', 'page': 1}
resp = requests.get(url, params=params)
print(resp.json())
