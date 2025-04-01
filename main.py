from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *
import logging
import re
from datetime import datetime
import os
import json
from collections import defaultdict
from decimal import Decimal, getcontext

# 设置Decimal精度
getcontext().prec = 10

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

    @staticmethod
    def trim_first_segment(data: str) -> str:
        """
        去除消息的第一行，保留后续所有内容（包括换行符和空格）
        """
        # 使用splitlines(True)保留换行符
        lines = data.splitlines(True)
        if not lines:
            return ''  # 如果没有内容，返回空字符串
        
        # 返回除第一行外的所有内容
        return ''.join(lines[1:])

    # 处理群组消息
    @handler(GroupNormalMessageReceived)
    async def handle_group_message(self, ctx: EventContext):
        # 获取原始消息
        msg = ctx.event.text_message
        # 去除第一行
        trimmed_msg = self.trim_first_segment(msg)
        
        # 检查处理后的消息是否只包含空白字符
        if trimmed_msg.strip():
            # 临时替换消息内容
            original_msg = ctx.event.text_message
            ctx.event.text_message = trimmed_msg
            
            # 处理消息
            await self.process_message(ctx)
            
            # 恢复原始消息
            ctx.event.text_message = original_msg
        else:
            # 如果处理后的消息只包含空白字符，则不处理
            pass


    # 统一处理消息的逻辑
    async def process_message(self, ctx: EventContext):
        self.ap.logger.info(f"接收到的上下文信息: {ctx},自己:{self},事件:{EventContext}")
        msg = ctx.event.text_message.strip()
        user_id = ctx.event.launcher_id
        
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
                logging.error(f"读取账单文件错误: {str(e)}")
                return {"balance": 0, "transactions": []}
        return {"balance": 0, "transactions": []}

    def save_user_data(self, user_id, data):
        file_path = os.path.join(self.data_dir, f"{user_id}.txt")
        logging.error(f"保存账单文件: {os.path.abspath(file_path)}")
        
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"保存账单文件错误: {str(e)}")
    
    # 使用Decimal计算以避免浮点数精度问题
    def calculate_expression(self, expression):
        # 替换表达式中的数字为Decimal
        expr = re.sub(r'(\d+(\.\d+)?)', r'Decimal("\1")', expression)
        # 计算结果
        result = eval(expr)
        # 转换为float并保留2位小数
        return float(result.quantize(Decimal('0.01')))

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
            
            # 使用Decimal计算以避免浮点数精度问题
            if expression.startswith('+'):
                amount = self.calculate_expression(expression[1:])
            else:
                amount = self.calculate_expression(expression)
            
            user_data = self.load_user_data(user_id)
            # 确保余额也使用2位小数
            user_data["balance"] = round(user_data["balance"] + amount, 2)
            
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
            logging.error(f"计算错误: {str(e)}")
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
        no_tag_amounts = []
        
        for transaction in transactions:
            amount = transaction["amount"]
            tag = transaction["tag"]
            
            if "#" in tag:
                # 提取#后面的标签
                tag_name = tag.split("#", 1)[1].strip()
                tag_groups[tag_name].append(amount)
            else:
                # 收集没有标签的交易
                no_tag_amounts.append(amount)
        
        # 输出每个标签的汇总
        for tag_name, amounts in tag_groups.items():
            total = sum(amounts)
            # 修改这里的汇总显示格式，处理负数
            formula_parts = []
            for amount in amounts:
                if amount >= 0:
                    formula_parts.append(f"+{amount:.2f}")
                else:
                    formula_parts.append(f"{amount:.2f}")
            
            # 将第一个数字的+号去掉（如果有）
            if formula_parts and formula_parts[0].startswith('+'):
                formula_parts[0] = formula_parts[0][1:]
                
            formula = "".join(formula_parts)
            reply += f"\n{tag_name}\n{formula}={total:.2f}\n"
        
        # 如果有无标签交易，也显示汇总
        if no_tag_amounts:
            total = sum(no_tag_amounts)
            # 修改这里的汇总显示格式，处理负数
            formula_parts = []
            for amount in no_tag_amounts:
                if amount >= 0:
                    formula_parts.append(f"+{amount:.2f}")
                else:
                    formula_parts.append(f"{amount:.2f}")
            
            # 将第一个数字的+号去掉（如果有）
            if formula_parts and formula_parts[0].startswith('+'):
                formula_parts[0] = formula_parts[0][1:]
                
            formula = "".join(formula_parts)
            reply += f"\n无标签\n{formula}={total:.2f}\n"
        
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
            "6. 显示功能列表: /记账 或 /记账功能\n"
            "================\n"
            "注意: #后面的文字会被识别为标签，用于分类统计"
        )
        ctx.add_return("reply", [features])
        ctx.prevent_default()

    def __del__(self):
        pass
