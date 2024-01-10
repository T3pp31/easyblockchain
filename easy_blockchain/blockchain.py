import datetime as dt
import hashlib
import json
import os


class BlockChain(object):
    def __init__(self):
        self.chain = []

    # make hash for first block
    def generate_random_hash(self):
        # making random data
        random_data = os.urandom(16)
        # hashing
        hash_object = hashlib.sha256(random_data)
        random_hash = hash_object.hexdigest()
        return random_hash

    # create new block
    def add_new_block(self, input_data, output_data):
        new_transaction = self.__create_new_transaction(input_data, output_data)

        # get previous block's hash
        if len(self.chain) > 0:
            prev_hash = self.chain[-1]["block_header"]["tran_hash"]
        else:
            prev_hash = generate_random_hash()

        # create transaction and connect
        new_block = {
            "block_index": len(self.chain) + 1,
            "block_item": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "block_header": {
                "prev_hash": prev_hash,
                "tran_hash": self.__hash(
                    prev_hash + self.__calc_tran_hash(new_transaction)
                ),
            },
            "tran_counter": len(input_data) + len(output_data),
            "tran_body": new_transaction,
        }
        self.chain.append(new_block)
        return new_block

    # create new transaction
    def __create_new_transaction(self, input_data, output_data):
        new_transaction = {
            "input_data": input_data,
            "output_data": output_data,
        }
        return new_transaction

    # calculate hash
    def __calc_tran_hash(self, new_transaction):
        tran_string = json.dumps(new_transaction, sort_keys=True).encode()
        return self.__hash(tran_string)

    def __hash(self, str_seed):
        return hashlib.sha256(str(str_seed).encode()).hexdigest()

    # print blockchain
    def dump(self,block_index=0):
        if block_index == 0:
            print(json.dumps(self.chain, sort_key=False, indent=2))

        else:
            print(json.dumps(self.chain(block_index, sort_key=False, indent=2)))


if __name__ == "__main__":
    bc = BlockChain()
