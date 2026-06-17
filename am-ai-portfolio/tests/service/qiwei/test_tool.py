import logging
import time
import requests
import json
from WXBizJsonMsgCrypt import WXBizJsonMsgCrypt

logger = logging.getLogger(__name__)

TOKEN = "hJqcu3uJ9Tn2gXPmxx2w9kkCkCE2EPYo"
AESKEY = "6qkdMrq68nTKduznJYO1A37W2oEgpkMUvkttRToqhUt"
RECIEVED = "ww1436e0e65a779aee"
wxcpt = WXBizJsonMsgCrypt(TOKEN , AESKEY, RECIEVED)

url = "http://localhost:8080/qiwei/"

timestamp = "1409659813"
nonce = "1372623149"

speekAsIWant = "上上下下左右左右baba"

body ={
    "msgtype": "text",
    "text": {
        "content": speekAsIWant
    }
}

ret, encrypt_msg= wxcpt.EncryptMsg(json.dumps(body), nonce, timestamp)
encrypt_msg = json.loads(encrypt_msg)
msg_signature = encrypt_msg['msgsignature']
timestamp = encrypt_msg['timestamp']
nonce = encrypt_msg['nonce']


response = requests.post(url, params={
    "msg_signature": msg_signature,
    "timestamp": timestamp,
    "nonce": nonce
}, json={
    "encrypt": encrypt_msg['encrypt'],
})
print("Response status code:", response.status_code)
print("Response content:", response.content)

text = []

resdic = response.json()
print(resdic)
    
ret, msg = wxcpt.DecryptMsg(
    response.content,
    resdic['msgsignature'],
    timestamp,
    nonce
)
msgdic = json.loads(msg)

finish = msgdic['stream']['finish']  
stream_id = msgdic['stream']['id']
text.append(msgdic['stream']['content'])


while not finish:
    body ={
    "msgtype": "stream",
    "stream": {
        "id": stream_id
    }
    }
    ret, encrypt_msg= wxcpt.EncryptMsg(json.dumps(body), nonce, timestamp)
    if ret != 0:
        logger.error("加密失败，错误码: %d", ret)
        break
    
    encrypt_msg = json.loads(encrypt_msg)
    msg_signature = encrypt_msg['msgsignature']
    timestamp = encrypt_msg['timestamp']
    nonce = encrypt_msg['nonce']

    time.sleep(0.1)

    response = requests.post(url, params={
        "msg_signature": msg_signature,
        "timestamp": timestamp,
        "nonce": nonce
    }, json={
        "encrypt": encrypt_msg['encrypt'],
    })
    # print("Response status code:", response.status_code)
    # print("Response content:", response.content)

    resdic = response.json()
    # print("Response JSON:", resdic)

    ret, msg = wxcpt.DecryptMsg(
        response.content,
        resdic['msgsignature'],
        timestamp,
        nonce
    )
    msgdic = json.loads(msg)
    finish = msgdic['stream']['finish']
    text.append(msgdic['stream']['content'])

    # print(msg)
print("".join(text))
