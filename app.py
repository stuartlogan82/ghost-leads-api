from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS, cross_origin
from os import environ
from twilio.rest import Client
from twilio.twiml.voice_response import Gather, VoiceResponse, Say, Redirect, Pause, Hangup
import requests
import json
# import pusher
from ably import AblyRest

load_dotenv()

TWILIO_ACCOUNT_SID = environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = environ.get('TWILIO_AUTH_TOKEN')
ABLY_API_KEY = environ.get('ABLY_API_KEY')
print(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, ABLY_API_KEY)
app = Flask(__name__)
CORS(app)

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
ably_client = AblyRest(ABLY_API_KEY)
ably_channel = ably_client.channels.get('calls')
# pusher_client = pusher.Pusher(
#     app_id='829962',
#     key='aada26f5e890d9c52291',
#     secret='d0cbb6e26fe8468f8532',
#     cluster='eu',
#     ssl=True
# )


def get_twilio_number():

    fetch_a_number = client.available_phone_numbers('GB').mobile.list(sms_enabled=True,
                                                                      voice_enabled=True,
                                                                      exclude_all_address_required=True,
                                                                      limit=1)
    twilio_phone_number = client.incoming_phone_numbers.create(
        phone_number=fetch_a_number[0].phone_number)
    print(twilio_phone_number.sid)

    return twilio_phone_number


def update_voice_url(sid):
    url = client \
        .incoming_phone_numbers(sid) \
        .update(
            voice_url='http://twilio-test.eu.ngrok.io/incoming_call'
        )
    return url


def update_sms_url(sid):
    url = client \
        .incoming_phone_numbers(sid) \
        .update(
            sms_url='http://twilio-test.eu.ngrok.io/incoming_sms'
        )
    return url


def send_sms_lead(to_num, from_num, body):
    client.messages.create(to=to_num, from_=from_num, body=body)


@app.route('/new_lead', methods=['GET'])
def new_lead():
    rep_number = request.args.get('rep_phone_number')
    print(f'REP NUMBER: {rep_number}')
    number = get_twilio_number()
    update_voice_url(number.sid)
    update_sms_url(number.sid)
    print(number.__dict__['_properties'])
    data = {
        "number": number.phone_number[1:],
        # "number": "447411272510",
        "call_count": 0,
        "sms_count": 0,
        "date_created": datetime.utcnow().isoformat(),
        "first_call_time": "",
        "last_call_time": ""
    }
    r = requests.post("http://localhost:3000/numbers", data=data)
    send_sms_lead(rep_number, number.phone_number,
                  f'You have a new lead! Please call this number ({number.phone_number}) to contact them')
    send_sms_lead("+447475737643", number.phone_number,
                  f'You have a new lead! Please call this number ({number.phone_number}) to contact them')
    return json.dumps(number.__dict__['_properties'], default=str), 200


@app.route('/incoming_call', methods=['POST'])
def incoming_call():
    called_num = request.form.get('To')[1:]
    response = VoiceResponse()
    response.pause(length=10)
    response.hangup()
    r = requests.get(f"http://localhost:3000/numbers?number={called_num}")
    id = r.json()[0]['id']
    count = int(r.json()[0]['call_count'])
    call_time = datetime.utcnow().isoformat()
    if count == 0:
        data = {"call_count": count + 1,
                "last_call_time": call_time,
                "first_call_time": call_time}
    else:
        data = {"call_count": count + 1,
                "last_call_time": call_time}
    print(data)
    headers = {"Content-Type": "application/json"}
    update = requests.patch(
        f"http://localhost:3000/numbers/{id}", json=data, headers=headers)
    print(update)
    # pusher_client.trigger('calls', 'new_call', {
    #                       'message': f'New call to {called_num}'})
    ably_channel.publish('new_call', f'New call to {called_num}')
    return str(response)


@app.route('/incoming_sms', methods=['POST'])
def incoming_sms():
    called_num = request.form.get('To')[1:]
    r = requests.get(f"http://localhost:3000/numbers?number={called_num}")
    id = r.json()[0]['id']
    count = int(r.json()[0]['sms_count'])
    data = {"sms_count": count + 1}
    print(data)
    headers = {"Content-Type": "application/json"}
    update = requests.patch(
        f"http://localhost:3000/numbers/{id}", json=data, headers=headers)
    print(update)
    # pusher_client.trigger('calls', 'new_call', {
    #                       'message': f'New call to {called_num}'})
    ably_channel.publish('new_call', f'New call to {called_num}')
    return 'OK', 200


@app.route('/delete', methods=['POST'])
def delete():
    id = request.args.get('id')
    num = requests.get(f"http://localhost:3000/numbers?id={id}")
    print(num.json())
    filter = f"+{num.json()[0]['number']}"
    incoming_phone_number = client.incoming_phone_numbers \
        .list(phone_number=filter, limit=1)
    print(incoming_phone_number[0].sid)
    try:
        client.incoming_phone_numbers(incoming_phone_number[0].sid).delete()
    except:
        return "Delete Failed", 404
    r = requests.delete(f"http://localhost:3000/numbers/{id}")
    return 'OK', 200
