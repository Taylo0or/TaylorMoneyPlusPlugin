from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
import re
from datetime import datetime
import os
import json

@register(name="TaylorMoneyPlusPlugin", description="Taylor记账插件", version="0.1", author="taylordang")
class MoneyPlusPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        self.host = host
        self.data_dir = "account_data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    async def initialize(self):
        pass

    # 处理个人消息
    @handler(PersonNormalMessageReceived)
    async def handle_person_message(self, ctx: EventContext):
        await self.process_message(ctx)

    # 处理群组消息
    @handler(GroupNormalMessageReceived)
    async def handle_group_message(self, ctx: EventContext):
        await self.process_message(ctx)

    # 统一处理消息的逻辑
    async def process_message(self, ctx: EventContext):
        msg = ctx.event.text_message.strip()
        user_id = ctx.event.sender_id
        
        if msg.startswith('+') or msg.startswith('-'):
            await self.process_transaction(ctx, msg, user_id)
        elif msg == "余额" or msg == "查询余额":
            await self.check_balance(ctx, user_id)
        elif msg == "帮助" or msg == "记账帮助":
            await self.show_help(ctx)

    def load_user_data(self, user_id):
        file_path = os.path.join(self.data_dir, f"{user_id}.txt")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return {"balance": 0, "transactions": []}

    def save_user_data(self, user_id, data):
        file_path = os.path.join(self.data_dir, f"{user_id}.txt")
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    async def process_transaction(self, ctx: EventContext, msg, user_id):
        try:
            parts = msg.split(' ', 1)
            expression = parts[0]
            description = parts[1] if len(parts) > 1 else "无描述"
            
            if expression.startswith('+'):
                amount = eval(expression[1:])
            else:
                amount = eval(expression)
            
            user_data = self.load_user_data(user_id)
            user_data["balance"] += amount
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_data["transactions"].append({
                "amount": amount,
                "expression": expression,
                "description": description,
                "timestamp": timestamp
            })
            
            self.save_user_data(user_id, user_data)
            
            amount_str = f"+{amount:.2f}" if amount > 0 else f"{amount:.2f}"
            reply = f"已记录: {amount_str}元 - {description}\n当前余额: {user_data['balance']:.2f}元"
            
        except Exception as e:
            self.host.logger.error(f"计算错误: {str(e)}")
            reply = f"计算错误，请检查表达式格式。正确格式如: +1*3 或 -5/2 [可选描述]"
        
        ctx.add_return("reply", [reply])
        ctx.prevent_default()

    async def check_balance(self, ctx: EventContext, user_id):
        user_data = self.load_user_data(user_id)
        reply = f"当前余额: {user_data['balance']:.2f}元"
        ctx.add_return("reply", [reply])
        ctx.prevent_default()

    async def show_help(self, ctx: EventContext):
        help_text = (
            "记账插件使用说明:\n"
            "1. 记录收入: +金额 [描述]\n"
            "   例如: +100 工资\n"
            "   支持简单计算: +50*2 双倍奖金\n"
            "2. 记录支出: -金额 [描述]\n"
            "   例如: -50 晚餐\n"
            "   支持简单计算: -20*3 购物\n"
            "3. 查询余额: 余额 或 查询余额\n"
            "4. 显示帮助: 帮助 或 记账帮助"
        )
        ctx.add_return("reply", [help_text])
        ctx.prevent_default()

    def __del__(self):
        pass
