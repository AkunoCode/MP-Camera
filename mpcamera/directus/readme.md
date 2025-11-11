(## Directus client (mpcamera.directus)

This small subpackage provides `DirectusClient`, a minimal synchronous HTTP
client to interact with your Directus instance.

Key features
- Read `DIRECTUS_API_URL` and `DIRECTUS_BEARER_TOKEN` from the environment
	(the package calls `load_dotenv()` so a local `.env` file works during dev).
- Convenience helpers for the app's collections:
	- `get_sites`, `get_soilsamples`, `get_microplastics` (GET)
	- `create_site`, `create_soilsample`, `create_microplastic` (POST)
	- `update_site`, `update_soilsample`, `update_microplastic` (PATCH)
	- `upload_file` for uploading images/files to Directus `/files`

Quick start

1. Install dependencies (from project root):

```powershell
pip install -r .\requirements.txt
```

2. Ensure your `.env` or environment contains:

```
DIRECTUS_API_URL=http://your-directus-host.example.com
DIRECTUS_BEARER_TOKEN=your_directus_token
```

3. Use the client:

```python
from mpcamera.directus import DirectusClient

## Directus client (mpcamera.directus)

This small subpackage provides `DirectusClient`, a minimal synchronous HTTP
client to interact with your Directus instance.

Key features
- Read `DIRECTUS_API_URL` and `DIRECTUS_BEARER_TOKEN` from the environment
  (the package calls `load_dotenv()` so a local `.env` file works during dev).
- Convenience helpers for the app's collections:
  - `get_sites`, `get_soilsamples`, `get_microplastics` (GET)
  - `create_site`, `create_soilsample`, `create_microplastic` (POST)
  - `update_site`, `update_soilsample`, `update_microplastic` (PATCH)
  - `upload_file` for uploading images/files to Directus `/files`

Quick start

1. Install dependencies (from project root):

```powershell
pip install -r .\requirements.txt
```

2. Ensure your `.env` or environment contains:

```
DIRECTUS_API_URL=http://your-directus-host.example.com
DIRECTUS_BEARER_TOKEN=your_directus_token
```

3. Use the client:

```python
from mpcamera.directus import DirectusClient

client = DirectusClient()

# Fetch sites
sites = client.get_sites(params={"fields": "*"})

# Upload an image then create a microplastic
upload = client.upload_file(r"C:\path\to\image.jpg")
file_id = upload.get("data", {}).get("id") or upload.get("id")

micro = {
    "image": file_id,
    "shape": "fiber",
    "color": "red",
    "confidence_level": "high",
}
resp = client.create_microplastic(micro)
print(resp)
```

Notes
- The client is synchronous and intentionally minimal. If you need async
  support, retry/backoff, or automatic pagination helpers, consider extending
  the client or ask me to add those features.
- After moving `directus.py` into this folder imports like
  `from mpcamera.directus import DirectusClient` will continue to work
  thanks to the `__init__.py` in this package.

Errors & debugging
- HTTP errors raise `requests.HTTPError`; see the logged response body
  for details (logging level DEBUG).

Getting, creating and updating — examples
----------------------------------------

Below are concrete examples for the common use cases: GET (retrieve), POST
(create), and PATCH (update) for the three collections used by the app.

1) GET (retrieve)

Fetch all sites (optionally request fields or apply filters using query params):

```python
from mpcamera.directus import DirectusClient

client = DirectusClient()
resp = client.get_sites(params={"fields": "*", "limit": 50})
# Directus returns JSON, usually under 'data'
sites = resp.get("data", resp)
print(len(sites))
```

Fetch soilsamples and microplastics with filters or expanded relations:

```python
# Example: get soilsamples for site id 1
soils = client.get_soilsamples(params={"filter[site][_eq]": 1, "limit": 100})

# Example: get microplastics but only specific fields
micro = client.get_microplastics(params={"fields": "id,image,shape,color,confidence_level"})
```

2) POST (create)

Create a new site:

```python
site = {
    "site_name": "Demo Farm",
    "owner": "Bob",
    "longitude": "151.2093",
    "latitude": "-33.8688",
    "crops": ["wheat", "barley"],
    "plastic_activity": ["plastic mulching"],
    "water_source": ["ground water"],
    "cultivation_practice": "integrated",
    "land_area_ha": "2.5",
}
create_site_resp = client.create_site(site)
print(create_site_resp)
```

Create a soilsample (site is a required m2o relation):

```python
soilsample = {
    "site": 1,
    "mass_kg": "0.5",
    "date_collected": "2025-09-13",
    "soil_type": "loam",
}
create_soil_resp = client.create_soilsample(soilsample)
print(create_soil_resp)
```

Create a microplastic. If you have a local image file, upload it first and use
the returned file id in the `image` field:

```python
upload_resp = client.upload_file(r"C:\path\to\image.jpg")
file_id = upload_resp.get("data", {}).get("id") or upload_resp.get("id")

micro_item = {
    "image": file_id,
    "shape": "fiber",
    "color": "red",
    "confidence_level": "high",
    "area_um2": "123.4",
}
create_micro_resp = client.create_microplastic(micro_item)
print(create_micro_resp)
```

3) PATCH (update)

Update a site's fields (partial update):

```python
site_id = 3
update_data = {"remarks": "Inspected 2025-09-20", "fiber_count": "12"}
resp = client.update_site(site_id, update_data)
print(resp)
```

Update a soilsample's mass:

```python
resp = client.update_soilsample(45, {"mass_kg": "0.75"})
```

Update a microplastic record (for example, post-processing corrections):

```python
resp = client.update_microplastic(123, {"color": "blue", "confidence_level": "medium"})
```

Best practices & notes
- Check the returned JSON: Directus tends to put the created/updated record
  under `data`, but some endpoints or Directus versions may return different
  shapes — inspect responses and adapt accordingly.
- For file uploads: `upload_file()` posts to `/files` and returns the created
  file record. Use the file `id` for any file relation fields.
- For large collections, implement pagination using Directus `limit` and
  `offset` (or cursor) query params.
- For resiliency, add retries/backoff around network calls (e.g., urllib3
  Retry or the `tenacity` library) when calling production APIs.

