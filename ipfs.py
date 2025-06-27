import requests
import json

PINATA_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySW5mb3JtYXRpb24iOnsiaWQiOiI1MDQ0ODFiYi1hMDFjLTRiMDMtODBmMi1jMDQ4NGIwYTU3ZDEiLCJlbWFpbCI6InhpbnlpZ3VAc2Vhcy51cGVubi5lZHUiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGluX3BvbGljeSI6eyJyZWdpb25zIjpbeyJkZXNpcmVkUmVwbGljYXRpb25Db3VudCI6MSwiaWQiOiJGUkExIn0seyJkZXNpcmVkUmVwbGljYXRpb25Db3VudCI6MSwiaWQiOiJOWUMxIn1dLCJ2ZXJzaW9uIjoxfSwibWZhX2VuYWJsZWQiOmZhbHNlLCJzdGF0dXMiOiJBQ1RJVkUifSwiYXV0aGVudGljYXRpb25UeXBlIjoic2NvcGVkS2V5Iiwic2NvcGVkS2V5S2V5IjoiMjFhYWI3NDE4MzY3NzExOTM3YzAiLCJzY29wZWRLZXlTZWNyZXQiOiJjZTEwYWRhYjA4N2Y4NDc2N2M2NmM3OGI0YjEwYmVkOWQ4MGNkZGFhNTMyZDE1MmMzYWE4NWZjNDUzZWVjZTNmIiwiZXhwIjoxNzgyNTIxMjgxfQ.m1yAVyEHWFZU7a7RjajriqGnN8EElGvMPVAWHSWAVMg"


def _pinata_headers():
	jwt = PINATA_JWT
	if not jwt:
		raise RuntimeError("PINATA JWT not set")
	return {
		"Authorization": f"Bearer {jwt}",
		"Content-Type": "application/json"
	}


def pin_to_ipfs(data):
	assert isinstance(data,dict), f"Error pin_to_ipfs expects a dictionary"
	#YOUR CODE HERE
	resp = requests.post(
		"https://api.pinata.cloud/pinning/pinJSONToIPFS",
		headers=_pinata_headers(),
		json={"pinataContent": data},
		timeout=30
	)
	resp.raise_for_status()
	cid = resp.json()["IpfsHash"]

	return cid

def get_from_ipfs(cid,content_type="json"):
	assert isinstance(cid,str), f"get_from_ipfs accepts a cid in the form of a string"
	#YOUR CODE HERE
	assert content_type.lower() == "json", "Only JSON content_type is supported"

	url = f"https://gateway.pinata.cloud/ipfs/{cid}"
	resp = requests.get(url, timeout=30)
	resp.raise_for_status()
	data = resp.json()

	assert isinstance(data,dict), f"get_from_ipfs should return a dict"
	return data

