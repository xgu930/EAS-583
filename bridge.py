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

def scan_blocks(chain: str, contract_info="contract_info.json"):
    """
    * source-mode :  Deposit events  ➜ wrap() on destination
    * destination :  Unwrap events  ➜ withdraw() on source
    The scan window is “last 5 blocks” or from the saved cursor onward.
    """
    if chain not in ("source", "destination"):
        print("Invalid chain:", chain)
        return

    w3_src = connect_to("source")
    w3_dst = connect_to("destination")

    src_cfg = get_contract_info("source", contract_info)
    dst_cfg = get_contract_info("destination", contract_info)

    C_src = w3_src.eth.contract(
        address=Web3.to_checksum_address(src_cfg["address"]),
        abi=src_cfg["abi"]
    )
    C_dst = w3_dst.eth.contract(
        address=Web3.to_checksum_address(dst_cfg["address"]),
        abi=dst_cfg["abi"]
    )

    acct  = Web3().eth.account.from_key(load_key())
    state = load_state()

    if chain == "source":                                   # ---------- Deposit → wrap
        head = w3_src.eth.block_number
        frm  = max(state.get("fuji", head - 5) + 1, head - 5)
        # one filter, one RPC call
        dep_filter = C_src.events.Deposit.create_filter(fromBlock=frm, toBlock=head)
        logs = dep_filter.get_all_entries()

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        for ev in logs:
            args = ev["args"]
            token, recipient, amount = args["token"], args["recipient"], args["amount"]
            print(f"[Fuji] Deposit {amount} {token} → {recipient}")

            tx = C_dst.functions.wrap(token, recipient, amount).build_transaction(
                {"from": acct.address,
                 "nonce": nonce,
                 "gas": 300_000,
                 "gasPrice": w3_dst.to_wei(10, "gwei")}
            )
            tx_hash = w3_dst.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("   ↳ wrap() tx:", tx_hash.hex())
            nonce += 1

        state["fuji"] = head                                   # advance cursor

    else:                                                      # ---------- Unwrap → withdraw
        head = w3_dst.eth.block_number
        frm  = max(state.get("bsc", head - 5) + 1, head - 5)
        un_filter = C_dst.events.Unwrap.create_filter(fromBlock=frm, toBlock=head)
        logs = un_filter.get_all_entries()

        nonce = w3_src.eth.get_transaction_count(acct.address)
        for ev in logs:
            args = ev["args"]
            underlying = args["underlying_token"]
            to_addr    = args["to"]
            amount     = args["amount"]
            print(f"[BSC] Unwrap {amount} {underlying} → {to_addr}")

            tx = C_src.functions.withdraw(underlying, to_addr, amount).build_transaction(
                {"from": acct.address,
                 "nonce": nonce,
                 "gas": 300_000,
                 "gasPrice": w3_src.to_wei(25, "gwei")}
            )
            tx_hash = w3_src.eth.send_raw_transaction(
                acct.sign_transaction(tx).raw_transaction)
            print("   ↳ withdraw() tx:", tx_hash.hex())
            nonce += 1

        state["bsc"] = head                                     # advance cursor

    save_state(state)
    