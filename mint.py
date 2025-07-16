from web3 import Web3, HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware

import secrets, json

w3   = Web3(HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))
w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

sk   = 0x49a174cad1f78a9891a9ce332dea5c4eee769fcb83f936cd5ba1d3e7baa022d9
acct = w3.eth.account.from_key(sk)

NFT  = "0x85ac2e065d4526FBeE6a2253389669a12318A412"
abi  = json.load(open("NFT.abi"))
nft  = w3.eth.contract(address=NFT, abi=abi)

nonce = secrets.token_bytes(32)
tx = nft.functions.claim(acct.address, nonce).build_transaction({
    "from":     acct.address,
    "nonce":    w3.eth.get_transaction_count(acct.address),
    "gas":      250_000,
    "gasPrice": w3.to_wei("25", "gwei"),
    "chainId":  43113,                 # Fuji
})
signed = acct.sign_transaction(tx)
w3.eth.send_raw_transaction(signed.raw_transaction)
print("Tx sent → wait ~5 s then check SnowTrace")
