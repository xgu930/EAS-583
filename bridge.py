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



def scan_blocks(chain, contract_info="contract_info.json"):
    """
    chain - (string) should be either "source" or "destination"
    Scan the last 5 blocks of the source and destination chains
    Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
    When Deposit events are found on the source chain, call the 'wrap' function on the destination chain
    When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return 0

    w3_src = connect_to('source')
    w3_dst = connect_to('destination')
    src = get_contract_info('source', contract_info)
    dst = get_contract_info('destination', contract_info)

    C_src = w3_src.eth.contract(src["address"], abi=src["abi"])
    C_dst = w3_dst.eth.contract(dst["address"], abi=dst["abi"])

    acct = Web3().eth.account.from_key(load_key())
    state = load_state()


    if chain == "source":  # ---------------- Deposit ➜ wrap
        head = w3_src.eth.block_number
        frm = max(state.get("fuji", head - 4) + 1, head - 4)  # newest 5 blocks
        to = head

        # topic‑filtered Deposit logs (cheapest possible RPC call)
        logs = C_src.events.Deposit.get_logs(from_block=frm, to_block=to)

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        for ev in logs:
            tkn, rcpt, amt = ev["args"]["token"], ev["args"]["recipient"], \
            ev["args"]["amount"]
            print(f"[Fuji] Deposit {amt} {tkn} → {rcpt}")

            tx = C_dst.functions.wrap(tkn, rcpt, amt).build_transaction({
                "from": acct.address,
                "nonce": nonce,
                "gas": 300_000,
                "gasPrice": w3_dst.to_wei(10, "gwei"),
            })
            tx_hash = w3_dst.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("   ↳ wrap() tx:", tx_hash.hex())
            nonce += 1

        state["fuji"] = head  # advance cursor
    else:  # ---------------- Unwrap ➜ withdraw
        head = w3_dst.eth.block_number
        frm = max(state.get("bsc", head - 4) + 1, head - 4)
        to = head

        logs = C_dst.events.Unwrap.get_logs(from_block=frm, to_block=to)

        nonce = w3_src.eth.get_transaction_count(acct.address)
        for ev in logs:
            args = ev["args"]
            u_tkn, to_addr, amt = args["underlying_token"], args["to"], args[
                "amount"]
            print(f"[BSC] Unwrap {amt} {u_tkn} → {to_addr}")

            tx = C_src.functions.withdraw(u_tkn, to_addr,
                                          amt).build_transaction({
                "from": acct.address,
                "nonce": nonce,
                "gas": 300_000,
                "gasPrice": w3_src.to_wei(25, "gwei"),
            })
            tx_hash = w3_src.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("   ↳ withdraw() tx:", tx_hash.hex())
            nonce += 1

        state["bsc"] = head  # advance cursor

    save_state(state)