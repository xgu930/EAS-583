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
    key = pathlib.Path(KEY_FILE).read_text().strip()
    return key if key.startswith("0x") else "0x"+key

def load_state() -> Dict[str,int]:
    if pathlib.Path(STATEFILE).exists():
        return json.loads(pathlib.Path(STATEFILE).read_text())
    return {}

def save_state(state: Dict[str,int]):
    pathlib.Path(STATEFILE).write_text(json.dumps(state))


def chunked_get_logs(event_contract, *, start_block: int, end_block: int,
                     step: int = 2, sleep_after: float = 0.3):
    """
    Stream logs for a single event (event_contract), fetching in small slices
    and shrinking the window when the RPC complains about “limit exceeded”.
    """
    cur = start_block
    while cur <= end_block:
        to_blk = min(cur + step - 1, end_block)
        try:
            # ↓ no explicit topics – ContractEvent.get_logs adds them
            logs = event_contract.get_logs(from_block=cur, to_block=to_blk)
            for ev in logs:
                yield ev

            time.sleep(sleep_after)
            cur = to_blk + 1

        except ValueError as err:
            if "limit exceeded" in str(err).lower():
                if step == 1:
                    print(f"[WARN] block {cur} still too heavy; skipping")
                    cur += 1
                else:
                    step = max(1, step // 2)
                    print(f"[WARN] limit exceeded; shrinking window to {step}")
                continue
            raise

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

    # Connect to both chains
    w3_src = connect_to('source')
    w3_dst = connect_to('destination')

    # Load the JSON info
    src_conf = get_contract_info('source', contract_info)
    dst_conf = get_contract_info('destination', contract_info)

    # Create contract instances
    Source = w3_src.eth.contract(
        address=Web3.to_checksum_address(src_conf["address"]),
        abi=src_conf["abi"]
    )
    Dest = w3_dst.eth.contract(
        address=Web3.to_checksum_address(dst_conf["address"]),
        abi=dst_conf["abi"]
    )

    # Load our account and last‐seen state
    acct = Web3().eth.account.from_key(load_key())
    state = load_state()

    if chain == 'source':
        head = w3_src.eth.block_number
        start = max(head - 4, 0)
        logs = chunked_get_logs(Source.events.Deposit, start_block=start,
                                end_block=head)

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        for ev in logs:
            args = ev['args']
            token, recipient, amount = args['token'], args['recipient'], args[
                'amount']
            print(f"[Fuji] Deposit {amount} {token} → {recipient}")

            tx = Dest.functions.wrap(token, recipient, amount).build_transaction({
                'from':     acct.address,
                'nonce':    nonce,
                'gas':      300_000,
                'gasPrice': w3_dst.to_wei(10, 'gwei'),
            })
            nonce += 1

            signed = acct.sign_transaction(tx)
            tx_hash = w3_dst.eth.send_raw_transaction(signed.raw_transaction)
            print("      ↳ wrap() tx:", tx_hash.hex())

        # update state cursor
        state['fuji'] = head

    else:
        head = w3_dst.eth.block_number
        start = max(head - 4, 0)
        logs = list(chunked_get_logs(Dest.events.Unwrap, start_block=start,
                                     end_block=head))
        nonce = w3_src.eth.get_transaction_count(acct.address)
        for ev in logs:
            args       = ev['args']
            underlying = args['underlying_token']
            wrapped    = args['wrapped_token']
            sender     = args['frm']
            to_addr    = args['to']
            amount     = args['amount']

            print(f"[BSC]  Unwrap {amount} {wrapped} → {to_addr} (from {sender})")

            tx = Source.functions.withdraw(underlying, to_addr, amount).build_transaction({
                'from':     acct.address,
                'nonce':    nonce,
                'gas':      300_000,
                'gasPrice': w3_src.to_wei(25, 'gwei'),
            })
            nonce += 1

            signed = acct.sign_transaction(tx)
            tx_hash = w3_src.eth.send_raw_transaction(signed.raw_transaction)
            print("      ↳ withdraw() tx:", tx_hash.hex())

        # update state cursor
        state['bsc'] = head

    save_state(state)