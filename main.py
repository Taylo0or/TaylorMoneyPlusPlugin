from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
import logging
import re
from datetime import datetime
import os
import json
from collections import defaultdict

@register(name="TaylorMoneyPlusPlugin", description="Taylor记账插件", version="0.1", author="taylordang")
class MoneyPlusPlugin(BasePlugin):

    def __init__(self, host: APIHost):
        self.host = host
        self.data_dir = os.path.abspath("account_data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        logging.error(f"账单数据目录: {self.data_dir}")

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
        elif msg in ["/清账", "/qz"]:
            await self.clear_account(ctx, user_id)
        elif msg in ["/查账", "/cz"]:
            await self.show_transactions(ctx, user_id)
        elif msg in ["/汇总", "/统计", "/total"]:
            await self.summarize_by_tag(ctx, user_id)
        elif msg in ["/记账功能"]:
            await self.show_features(ctx)

    def load_user_data(self, user_id):
        file_path = os.path.join(self.data_dir, f"{user_id}.txt")
        logging.error(f"加载账单文件: {os.path.abspath(file_path)}")
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                self.host.logger.error(f"读取账单文件错误: {str(e)}")
                return {"balance": 0, "transactions": []}
        return {"balance": 0, "transactions": []}

    def save_user_data(self, user_id, data):
        file_path = os.path.join(self.data_dir, f"{user_id}.txt")
        logging.error(f"保存账单文件: {os.path.abspath(file_path)}")
        
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.host.logger.error(f"保存账单文件错误: {str(e)}")

    async def process_transaction(self, ctx: EventContext, msg, user_id):
        try:
            # 检查是否有标签
            tag = ""
            if "#" in msg:
                parts = msg.split("#", 1)
                msg = parts[0].strip()
                tag = "#" + parts[1].strip()
            
            # 处理表达式
            parts = msg.split(' ', 1)
            expression = parts[0]
            description = parts[1] if len(parts) > 1 else ""
            
            # 如果有描述，将其添加到标签前
            if description:
                tag = description + " " + tag if tag else description
            
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
                "tag": tag,
                "timestamp": timestamp
            })
            
            self.save_user_data(user_id, user_data)
            
            amount_str = f"+{amount:.2f}" if amount > 0 else f"{amount:.2f}"
            reply = f"已记录: {amount_str}元 {tag}\n================\n账单金额: {user_data['balance']:.2f}"
            ctx.add_return("reply", [reply])
            ctx.prevent_default()
            
        except Exception as e:
            # 计算错误时不返回任何信息，只记录日志
            self.host.logger.error(f"计算错误: {str(e)}")
            ctx.prevent_default()

    async def clear_account(self, ctx: EventContext, user_id):
        # 清空账户
        user_data = {"balance": 0, "transactions": []}
        self.save_user_data(user_id, user_data)
        
        reply = (
            "清账成功\n"
            "================\n"
            "账单金额: 0.00\n"
            "================"
        )
        ctx.add_return("reply", [reply])
        ctx.prevent_default()

    async def show_transactions(self, ctx: EventContext, user_id):
        user_data = self.load_user_data(user_id)
        balance = user_data["balance"]
        transactions = user_data["transactions"]
        
        if not transactions:
            reply = "账单金额: 0.00"
            ctx.add_return("reply", [reply])
            ctx.prevent_default()
            return
        
        reply = f"账单金额: {balance:.2f}\n=====账单明细=====\n"
        
        for transaction in transactions:
            amount = transaction["amount"]
            tag = transaction["tag"]
            amount_str = f"+{amount}" if amount > 0 else f"{amount}"
            reply += f"{amount_str}={amount:.2f} {tag}\n"
        
        reply += "================"
        ctx.add_return("reply", [reply])
        ctx.prevent_default()

    async def summarize_by_tag(self, ctx: EventContext, user_id):
        user_data = self.load_user_data(user_id)
        balance = user_data["balance"]
        transactions = user_data["transactions"]
        
        if not transactions:
            reply = "账单金额: 0.00"
            ctx.add_return("reply", [reply])
            ctx.prevent_default()
            return
        
        # 先显示所有交易
        reply = f"账单金额: {balance:.2f}\n=====账单明细=====\n"
        
        for transaction in transactions:
            amount = transaction["amount"]
            tag = transaction["tag"]
            amount_str = f"+{amount}" if amount > 0 else f"{amount}"
            reply += f"{amount_str}={amount:.2f} {tag}\n"
        
        reply += "================\n"
        
        # 按标签分组汇总
        tag_groups = defaultdict(list)
        
        for transaction in transactions:
            tag = transaction["tag"]
            if "#" in tag:
                # 提取#后面的标签
                tag_name = tag.split("#", 1)[1].strip()
                tag_groups[tag_name].append(transaction["amount"])
        
        # 输出每个标签的汇总
        for tag_name, amounts in tag_groups.items():
            total = sum(amounts)
            amounts_str = "+".join([f"{amount:.2f}" for amount in amounts])
            reply += f"\n{tag_name}\n{amounts_str}={total:.2f}\n"
        
        reply += "\n================"
        ctx.add_return("reply", [reply])
        ctx.prevent_default()

    async def show_features(self, ctx: EventContext):
        features = (
            "记账插件功能列表:\n"
            "================\n"
            "1. 记录收入: +金额 [描述] [#标签]\n"
            "   例如: +100 工资 #收入\n"
            "   支持计算: +50*2 #奖金\n\n"
            "2. 记录支出: -金额 [描述] [#标签]\n"
            "   例如: -50 晚餐 #餐饮\n"
            "   支持计算: -20*3 购物 #日用\n\n"
            "3. 查看账单: /查账 或 /cz\n"
            "4. 清空账单: /清账 或 /qz\n"
            "5. 按标签汇总: /汇总 或 /统计 或 /total\n"
            "6. 显示功能列表: /记账\n"
            "================\n"
            "注意: #后面的文字会被识别为标签，用于分类统计"
        )
        ctx.add_return("reply", [features])
        ctx.prevent_default()

    def __del__(self):
        pass
