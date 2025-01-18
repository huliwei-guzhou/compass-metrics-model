from compass_metrics.db_dsl import (get_updated_since_query,
                                    get_uuid_count_query,
                                    get_message_list_query,
                                    get_pr_query_by_commit_hash)
from compass_metrics.contributor_metrics import get_contributor_list
from compass_metrics.repo_metrics import get_activity_repo_list
from compass_common.datetime import (get_time_diff_months,
                                     check_times_has_overlap,
                                     get_oldest_date,
                                     get_latest_date,
                                     get_date_list)
from compass_common.list_utils import split_list                                     
from datetime import timedelta, datetime
from compass_common.opensearch_utils import get_all_index_data
import numpy as np
import math
from dateutil.relativedelta import relativedelta
from typing import List
from .git_metrics import commit_count

def activity_quarterly_contribution(client, contributors_index: str, repo_list: List[str], date: datetime = None) -> dict:
    """
    获取最近一年中每季度的代码贡献量。
    
    参数：
        client: 数据库客户端
        contributors_index: 贡献者索引名称
        repo_list: 仓库列表
        date: 评估日期（默认为当前日期）
    
    返回：
        dict: 包含季度贡献量的统计数据，包括：
            - activity_quarterly_contribution: 所有贡献量
            - activity_quarterly_contribution_bot: 机器人贡献量
            - activity_quarterly_contribution_without_bot: 非机器人贡献量
    """
    if date is None:
        date = datetime.now()
    
    result = []
    result_bot = []
    result_without_bot = []
    
    # 获取当前季度的结束时间（将日期调整到季度末）
    current_quarter_end = date.replace(
        month=((date.month - 1) // 3 * 3 + 3),
        day=1
    )
    # 调整到月末
    if current_quarter_end.month == 3:
        current_quarter_end = current_quarter_end.replace(day=31)
    elif current_quarter_end.month == 6:
        current_quarter_end = current_quarter_end.replace(day=30)
    elif current_quarter_end.month == 9:
        current_quarter_end = current_quarter_end.replace(day=30)
    elif current_quarter_end.month == 12:
        current_quarter_end = current_quarter_end.replace(day=31)
    
    # 计算最近4个季度的贡献量
    for i in range(4):
        # 计算季度的起止时间
        quarter_end = current_quarter_end - relativedelta(months=3 * i)
        quarter_start = quarter_end - relativedelta(months=3) + timedelta(days=1)
        
        quarter_data = commit_count(
            client,
            contributors_index,
            quarter_end,
            repo_list,
            from_date=quarter_start
        )
        
        result.append(quarter_data['commit_count'])
        result_bot.append(quarter_data['commit_count_bot'])
        result_without_bot.append(quarter_data['commit_count_without_bot'])
    
    return {
        'activity_quarterly_contribution': result,
        'activity_quarterly_contribution_bot': result_bot,
        'activity_quarterly_contribution_without_bot': result_without_bot
    }