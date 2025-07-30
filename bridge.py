from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import pandas as pd
import json, pathlib, sys, os
from typing import Dict
import time
from functools import partial


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


def chunked_get_logs(event_filter_fn, *, start_block: int, end_block: int,
                     step: int = 250, max_retry: int = 6):
    """
    Fetch logs in <step>-block chunks. Retries on RPC 'limit exceeded'
    (code −32005 or plain‑text message), backing off with time.sleep().
    """
    cur = start_block
    while cur <= end_block:
        window_end = min(cur + step - 1, end_block)

        for attempt in range(1, max_retry + 1):
            try:
                yield from event_filter_fn(from_block=cur, to_block=window_end)
                break
            except ValueError as err:
                # Handles BOTH dict‑style and string‑style errors
                msg = str(err).lower()
                if ("limit exceeded" in msg or      # string form
                    (isinstance(err.args[0], dict) and
                     err.args[0].get("code") == -32005)):  # dict form
                    time.sleep(attempt)
                    continue
                raise
        cur = window_end + 1

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

    if chain == "source":
        head = w3_src.eth.block_number
        frm = st.get("fuji", head - 1) + 1

        logs = chunked_get_logs(
            Source.events.Deposit.get_logs,
            start_block=frm,
            end_block=head
        )

        nonce_dst = w3_dst.eth.get_transaction_count(acct.address)

        for ev in logs:
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
        frm = st.get("bsc", head - 1) + 1
        logs = chunked_get_logs(
            Dest.events.Unwrap.get_logs,
            start_block=frm,
            end_block=head
        )

        nonce_src = w3_src.eth.get_transaction_count(acct.address)

        for ev in logs:
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

