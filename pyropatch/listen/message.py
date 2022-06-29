# this code snippet is created using
# https://github.com/usernein/pyromod/blob/master/pyromod/listen/listen.py

from typing import Union, Optional, AsyncGenerator
from ..utils import patch, patchable
import pyrogram, re
import asyncio
import functools

loop = asyncio.get_event_loop()


class ListenerCanceled(Exception):
    pass


pyrogram.errors.ListenerCanceled = ListenerCanceled


@patch(pyrogram.client.Client)
class Client():

    @patchable
    async def listen_message(self, chat_id, filters=None, timeout=None):
        if type(chat_id) != int:
            chat = await self.get_chat(chat_id)
            chat_id = chat.id
        future = loop.create_future()
        future.add_done_callback(
            functools.partial(self.remove_message_listener, chat_id)
        )
        self.msg_listeners.update({
            chat_id: {"future": future, "filters": filters}
        })
        return await asyncio.wait_for(future, timeout)

    @patchable
    async def ask_message(self, chat_id, text, filters=None, timeout=None, *args, **kwargs):
        request = await self.send_message(chat_id, text, *args, **kwargs)
        response = await self.listen_message(chat_id, filters, timeout)
        response.request = request
        return response

    @patchable
    def remove_message_listener(self, chat_id, future):
        if future == self.msg_listeners[chat_id]["future"]:
            self.msg_listeners.pop(chat_id, None)

    @patchable
    def cancel_message_listener(self, chat_id):
        listener = self.msg_listeners.get(chat_id)
        if not listener or listener['future'].done():
            return
        listener['future'].set_exception(ListenerCanceled())
        self.remove_message_listener(chat_id, listener['future'])
         
    @patchable
    async def iter_messages(
        self,
        chat_id: Union[int, str],
        limit: int,
        offset: int = 0,
        skip_duplicate_files: bool = False,
    ) -> Optional[AsyncGenerator["types.Message", None]]:
        
        MESSAGES = []
        current = offset
        while True:
            new_diff = min(200, limit - current)
            if new_diff <= 0:
                return 
            messages = await self.get_messages(chat_id, list(range(current, current+new_diff+1)))
            for message in messages:
                if skip_duplicate_files:
                    if isinstance(message.media, "document"):
                       file_id = message.document.file_id
                       if file_id in MESSAGES:
                          message = "DUPLICATE"
                       else:
                          MESSAGES.append(file_id)
                yield message
                current += 1
       
     @patchable
     async def start_clone_bot(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        session_name: str = ":memory:",
        stop_client: bool = None
    ):
    
    bot = Client(
       session_name, 
       api_id, 
       api_hash, 
       bot_token=bot_token
       )
    
    try: 
       await bot.start()
    except Exception:
       raise Exception("The given bot token is expired or invalid. please change it !")
    bot.details = await bot.get_me()
    if stop_client:
       await bot.stop()  
    return bot 

@patch(pyrogram.types.messages_and_media.message.Message)
class Message():
    @patchable
    def get_bot_token(self) -> str:
        bot_token = re.findall(r'\d[0-9]{8,10}:[0-9A-Za-z_-]{35}', self.text, re.IGNORECASE)
        return bot_token[0] if bot_token else None
    
@patch(pyrogram.handlers.message_handler.MessageHandler)
class MessageHandler():
    @patchable
    def __init__(self, callback: callable, filters=None):
        self.user_callback = callback
        self.old___init__(self.resolve_listener, filters)

    @patchable
    async def resolve_listener(self, client, message, *args):
        listener = client.msg_listeners.get(message.chat.id)
        if listener and not listener['future'].done():
            listener['future'].set_result(message)
        else:
            if listener and listener['future'].done():
                client.clear_listener(message.chat.id, listener['future'])
            await self.user_callback(client, message, *args)

    @patchable
    async def check(self, client, update):
        listener = client.msg_listeners.get(update.chat.id)

        if listener and not listener['future'].done():
            return await listener['filters'](client, update) if callable(listener['filters']) else True

        return (
            await self.filters(client, update)
            if callable(self.filters)
            else True
        )
