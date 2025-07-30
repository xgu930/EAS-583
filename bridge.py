from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import pandas as pd
import json, pathlib, sys, os
from typing import Dict, Any


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]


KEY_FILE  = "secret_key.txt"     # same file you used earlier
STATEFILE = ".bridge.last"       # remember last processed block

def load_key() -> str:
    key = pathlib.Path(KEY_FILE).read_text().strip()
    return key if key.startswith("0x") else "0x"+key

def load_state() -> Dict[str,int]:
    if pathlib.Path(STATEFILE).exists():
        return json.loads(pathlib.Path(STATEFILE).read_text())
    return {}

def save_state(state: Dict[str,int]):
    pathlib.Path(STATEFILE).write_text(json.dumps(state))


def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
        #YOUR CODE HERE

    w3_src = connect_to('source')
    w3_dst = connect_to('destination')

    info = json.load(open(contract_info))
    src_conf = info["source"]
    dst_conf = info["destination"]

    Source = w3_src.eth.contract(
        address=Web3.to_checksum_address(src_conf["address"].strip()),
        abi=src_conf["abi"]
    )
    Dest = w3_dst.eth.contract(
        address=Web3.to_checksum_address(dst_conf["address"].strip()),
        abi=dst_conf["abi"]
    )

    acct = Web3().eth.account.from_key(load_key())

    st = load_state()
    last_fuji = st.get("fuji", 0)
    last_bsc = st.get("bsc", 0)

    if chain == "source":
        head = w3_src.eth.block_number
        frm = max(0, head - 5) if last_fuji == 0 else last_fuji + 1
        deposits = Source.events.Deposit.get_logs(from_block=frm, to_block=head)
        nonce_dst = w3_dst.eth.get_transaction_count(acct.address)

        for ev in deposits:
            tok, recipient, amount = ev["args"].values()
            print(f"[Fuji] Deposit {amount} {tok} → {recipient}")

            tx = Dest.functions.wrap(tok, recipient, amount).build_transaction(
                {
                    "from": acct.address,
                    "nonce": nonce_dst,
                    "gas": 300_000,
                    "gasPrice": w3_dst.to_wei(10, "gwei"),  # legacy on BSC‑t
                })
            nonce_dst += 1
            sent = w3_dst.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("      ↳ wrap() tx:", sent.hex())

        st["fuji"] = head

    elif chain == "destination":
        head = w3_dst.eth.block_number
        frm = max(0, head - 5) if last_bsc == 0 else last_bsc + 1
        unwraps = Dest.events.Unwrap.get_logs(from_block=frm, to_block=head)

        nonce_src = w3_src.eth.get_transaction_count(acct.address)

        for ev in unwraps:
            underlying, wrapped, frm_addr, to, amount = ev["args"].values()
            print(f"[BSC]  Unwrap {amount} {wrapped} → {to}")

            tx = Source.functions.withdraw(
                underlying, to, amount
            ).build_transaction({
                "from": acct.address,
                "nonce": nonce_src,
                "gas": 300_000,
                "gasPrice": w3_src.to_wei(25, "gwei"),
            })
            nonce_src += 1
            sent = w3_src.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("      ↳ withdraw() tx:", sent.hex())

        st["bsc"] = head

    save_state(st)

