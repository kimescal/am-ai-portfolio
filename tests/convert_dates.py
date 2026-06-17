#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV日期格式转换脚本
功能：将CSV文件中所有日期相关列的格式从 "2001/1/1" 转换为 "2001-1-1"
"""

import pandas as pd
import re
import sys
import os
from typing import List, Union
import argparse


def is_date_like(value: str) -> bool:
    """
    判断字符串是否像日期格式
    支持的格式：YYYY/M/D, YYYY/MM/DD, M/D/YYYY, MM/DD/YYYY 等
    """
    if not isinstance(value, str) or not value.strip():
        return False
    
    # 匹配各种日期格式的正则表达式
    date_patterns = [
        r'^\d{4}/\d{1,2}/\d{1,2}$',      # YYYY/M/D 或 YYYY/MM/DD
        r'^\d{1,2}/\d{1,2}/\d{4}$',      # M/D/YYYY 或 MM/DD/YYYY
        r'^\d{4}/\d{1,2}$',              # YYYY/M 或 YYYY/MM
        r'^\d{1,2}/\d{4}$',              # M/YYYY 或 MM/YYYY
    ]
    
    return any(re.match(pattern, value.strip()) for pattern in date_patterns)


def convert_date_format(value: str) -> str:
    """
    将日期格式从斜杠转换为短横线
    """
    if pd.isna(value) or not isinstance(value, str):
        return value
    
    # 去除前后空格
    value = value.strip()
    
    # 如果包含斜杠且看起来像日期，则转换
    if '/' in value and is_date_like(value):
        return value.replace('/', '-')
    
    return value


def detect_date_columns(df: pd.DataFrame, sample_size: int = 100) -> List[str]:
    """
    自动检测包含日期数据的列
    """
    date_columns = []
    
    for column in df.columns:
        # 取样本数据进行检测
        sample_data = df[column].dropna().astype(str).head(sample_size)
        
        if len(sample_data) == 0:
            continue
            
        # 计算看起来像日期的数据比例
        date_like_count = sum(1 for value in sample_data if is_date_like(value))
        date_ratio = date_like_count / len(sample_data)
        
        # 如果超过50%的数据看起来像日期，则认为是日期列
        if date_ratio > 0.5:
            date_columns.append(column)
            print(f"检测到日期列: '{column}' (日期格式数据比例: {date_ratio:.2%})")
    
    return date_columns


def convert_csv_dates(input_file: str, output_file: str = None, 
                     specific_columns: List[str] = None, 
                     encoding: str = 'utf-8') -> None:
    """
    转换CSV文件中的日期格式
    
    Args:
        input_file: 输入CSV文件路径
        output_file: 输出CSV文件路径（如果为None，则覆盖原文件）
        specific_columns: 指定要转换的列名列表（如果为None，则自动检测）
        encoding: 文件编码
    """
    
    # 检查输入文件是否存在
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"文件不存在: {input_file}")
    
    print(f"正在读取文件: {input_file}")
    
    # 尝试不同的编码读取文件
    encodings_to_try = [encoding, 'utf-8', 'gbk', 'gb2312', 'latin1']
    df = None
    
    for enc in encodings_to_try:
        try:
            df = pd.read_csv(input_file, encoding=enc)
            print(f"成功使用编码 '{enc}' 读取文件")
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"使用编码 '{enc}' 读取失败: {e}")
            continue
    
    if df is None:
        raise Exception("无法读取文件，请检查文件格式和编码")
    
    print(f"文件包含 {len(df)} 行, {len(df.columns)} 列")
    
    # 确定要转换的列
    if specific_columns:
        # 使用指定的列
        columns_to_convert = [col for col in specific_columns if col in df.columns]
        missing_columns = [col for col in specific_columns if col not in df.columns]
        
        if missing_columns:
            print(f"警告: 以下指定列不存在: {missing_columns}")
        
        print(f"将转换指定列: {columns_to_convert}")
    else:
        # 自动检测日期列
        print("自动检测日期列...")
        columns_to_convert = detect_date_columns(df)
    
    if not columns_to_convert:
        print("未找到需要转换的日期列")
        return
    
    # 转换日期格式
    conversion_count = 0
    for column in columns_to_convert:
        print(f"正在转换列: '{column}'")
        original_values = df[column].copy()
        df[column] = df[column].apply(convert_date_format)
        
        # 统计转换数量
        changed_count = sum(1 for old, new in zip(original_values, df[column]) 
                          if str(old) != str(new))
        conversion_count += changed_count
        print(f"  转换了 {changed_count} 个值")
    
    # 保存文件
    if output_file is None:
        output_file = input_file
        print(f"将覆盖原文件: {output_file}")
    else:
        print(f"将保存到新文件: {output_file}")
    
    df.to_csv(output_file, index=False, encoding=encoding)
    print(f"转换完成! 总共转换了 {conversion_count} 个日期值")


def main():
    """
    命令行主函数
    """
    parser = argparse.ArgumentParser(description='CSV日期格式转换工具')
    parser.add_argument('input_file', help='输入CSV文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认覆盖原文件）')
    parser.add_argument('-c', '--columns', nargs='+', help='指定要转换的列名')
    parser.add_argument('-e', '--encoding', default='utf-8', help='文件编码（默认utf-8）')
    
    args = parser.parse_args()
    
    try:
        convert_csv_dates(
            input_file=args.input_file,
            output_file=args.output,
            specific_columns=args.columns,
            encoding=args.encoding
        )
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


# 使用示例
if __name__ == "__main__":
    # 如果直接运行脚本，可以在这里修改参数进行测试
    if len(sys.argv) == 1:
        # 测试模式 - 修改这里的参数
        test_file = "portfolio_info.csv"  # 修改为你的文件路径
        
        if os.path.exists(test_file):
            print("测试模式运行...")
            convert_csv_dates(
                input_file=test_file,
                output_file="portfolio_info_converted.csv",  # 输出到新文件
                # specific_columns=['日期列1', '日期列2'],  # 或者指定特定列
                encoding='utf-8'
            )
        else:
            print("请通过命令行参数运行，或修改test_file变量指向正确的文件路径")
            print("使用方法:")
            print("  python script.py input_file.csv")
            print("  python script.py input_file.csv -o output_file.csv")
            print("  python script.py input_file.csv -c 列名1 列名2")
    else:
        main()