from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import pandas as pd
import json, pathlib
from typing import Dict
import time



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


KEY_FILE  = "secret_key.txt"
STATEFILE = ".bridge.last"

def load_key() -> str:
    raw = pathlib.Path(KEY_FILE).read_text().strip()
    return raw if raw.startswith("0x") else "0x"+raw


def load_state() -> Dict[str,int]:
    if pathlib.Path(STATEFILE).exists():
        return json.loads(pathlib.Path(STATEFILE).read_text())
    return {}


def save_state(state: Dict[str,int]):
    pathlib.Path(STATEFILE).write_text(json.dumps(state))



def chunked_get_logs(event_contract, *, start_block, end_block,
                     step=2, sleep_after=0.3):
    cur = start_block
    while cur <= end_block:
        to_blk = min(cur + step - 1, end_block)
        try:
            for ev in event_contract.get_logs(from_block=cur, to_block=to_blk):
                yield ev
            time.sleep(sleep_after)
            cur = to_blk + 1
        except ValueError as err:
            if "-32005" in str(err):
                if step <= 1:
                    print(f"[WARN] block {cur} too noisy; skipping")
                    cur += 1
                else:
                    step //= 2
                    print(f"[WARN] limit exceeded; step→{step}")
                continue
            raise


def scan_blocks(chain, contract_info="contract_info.json"):

    if chain not in ("source", "destination"):
        print("Invalid chain:", chain); return

    w3_src = connect_to("source")
    w3_dst = connect_to("destination")
    src = get_contract_info("source", contract_info)
    dst = get_contract_info("destination", contract_info)

    C_src = w3_src.eth.contract(address=Web3.to_checksum_address(src["address"]),
                                abi=src["abi"])
    C_dst = w3_dst.eth.contract(address=Web3.to_checksum_address(dst["address"]),
                                abi=dst["abi"])

    acct  = Web3().eth.account.from_key(load_key())
    state = load_state()


    if chain == "source":
        head = w3_src.eth.block_number
        frm  = max(state.get("fuji", head-100) + 1, head-100)
        logs = chunked_get_logs(C_src.events.Deposit,
                                start_block=frm, end_block=head)

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        for ev in logs:
            t,r,a = ev["args"]["token"], ev["args"]["recipient"], ev["args"]["amount"]
            print(f"[Fuji] Deposit {a} {t} → {r}")
            tx = C_dst.functions.wrap(t,r,a).build_transaction({
                "from": acct.address, "nonce": nonce,
                "gas": 300_000, "gasPrice": w3_dst.to_wei(10,"gwei")
            })
            signed = acct.sign_transaction(tx)
            print("   ↳ wrap() tx:", w3_dst.eth.send_raw_transaction(
                  signed.raw_transaction).hex())
            nonce += 1
        state["fuji"] = head

    else:
        head = w3_dst.eth.block_number
        frm  = max(state.get("bsc", head-100) + 1, head-100)
        logs = list(chunked_get_logs(C_dst.events.Unwrap,
                                     start_block=frm, end_block=head))
        nonce = w3_src.eth.get_transaction_count(acct.address)
        for ev in logs:
            args = ev["args"]
            u,to_addr,a = args["underlying_token"], args["to"], args["amount"]
            print(f"[BSC]  Unwrap {a} {u} → {to_addr}")
            tx = C_src.functions.withdraw(u,to_addr,a).build_transaction({
                "from": acct.address, "nonce": nonce,
                "gas": 300_000, "gasPrice": w3_src.to_wei(25,"gwei")
            })
            signed = acct.sign_transaction(tx)
            print("   ↳ withdraw() tx:",
                  w3_src.eth.send_raw_transaction(signed.raw_transaction).hex())
            nonce += 1
        state["bsc"] = head

    save_state(state)