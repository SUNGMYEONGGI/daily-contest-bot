#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Kaggle과 Dacon의 대회 정보를 수집하여 Slack으로 알림을 보내는 봇
"""

# Standard library imports
import os
import json
import time
import logging
from datetime import datetime

# Third-party imports
import schedule
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from kaggle.api.kaggle_api_extended import KaggleApi


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("competition_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()

# 상수 정의
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#contest-notify-bot")
DATA_FILE = "competition_data.json"

# Slack 클라이언트 초기화
slack_client = WebClient(token=SLACK_TOKEN)


def save_competition_data(competitions):
    """대회 데이터를 JSON 파일로 저장하는 함수.

    Args:
        competitions (list): 저장할 대회 정보 리스트. 각 대회는 딕셔너리 형태로 저장됨

    Returns:
        None

    Raises:
        Exception: 파일 저장 중 오류 발생 시
    """
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(competitions, f, ensure_ascii=False, indent=2)
        logger.info("Competition data saved successfully")
    except Exception as e:
        logger.error(f"Error saving competition data: {e}")


def load_competition_data():
    """저장된 대회 데이터를 JSON 파일에서 로드하는 함수.

    Returns:
        list: 저장된 대회 정보 리스트. 파일이 없거나 오류 발생 시 빈 리스트 반환

    Raises:
        Exception: 파일 로드 중 오류 발생 시
    """
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        logger.error(f"Error loading competition data: {e}")
        return []


def find_new_competitions(current_competitions, previous_competitions):
    """현재 대회 목록과 이전 대회 목록을 비교하여 새로운 대회를 찾는 함수.

    Args:
        current_competitions (list): 현재 크롤링된 대회 정보 리스트
        previous_competitions (list): 이전에 저장된 대회 정보 리스트

    Returns:
        list: 새로 추가된 대회 정보 리스트
    """
    current_urls = {comp['url'] for comp in current_competitions}
    previous_urls = {comp['url'] for comp in previous_competitions}
    new_urls = current_urls - previous_urls
    
    return [comp for comp in current_competitions if comp['url'] in new_urls]


def get_kaggle_competitions():
    """Kaggle API를 사용하여 현재 진행 중인 대회 정보를 가져오는 함수.

    Returns:
        list: Kaggle 대회 정보 리스트. 각 대회는 딕셔너리 형태로 저장
              (platform, name, description, url, deadline, category, reward 포함)

    Raises:
        Exception: Kaggle API 호출 중 오류 발생 시
    """
    try:
        api = KaggleApi()
        api.authenticate()
        logger.info("Kaggle API 인증 성공")
        
        competitions = api.competitions_list()
        competition_list = []
        
        for comp in competitions:
            if comp.deadline > datetime.now():
                # URL 중복 방지: comp.ref가 이미 전체 URL인지 확인
                if comp.ref.startswith('http'):
                    url = comp.ref
                else:
                    url = f"https://www.kaggle.com/competitions/{comp.ref}"
                
                competition_list.append({
                    'platform': 'Kaggle',
                    'name': comp.title,
                    'description': comp.description,
                    'url': url,
                    'deadline': comp.deadline.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    'category': comp.category,
                    'reward': f"${comp.reward}"
                })
                logger.info(f"Found Kaggle competition: {comp.title}")
        
        return competition_list
    except Exception as e:
        logger.error(f"Error getting Kaggle competitions: {e}")
        return []


def get_competition_period(detail_url):
    """Dacon 대회의 기간 정보를 크롤링하는 함수.

    Args:
        detail_url (str): 대회 상세 페이지 URL

    Returns:
        str: 대회 기간 정보 문자열 또는 None (크롤링 실패 시)

    Raises:
        Exception: 웹 크롤링 중 오류 발생 시
    """
    try:
        response = requests.get(detail_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        period_text = soup.find(
            string=lambda text: text and '대회 기간 :' in text
        )
        
        if period_text:
            return period_text.replace('- 대회 기간 : ', '').strip()
        return "기간 정보를 찾을 수 없습니다."
    except Exception as e:
        logger.error(f"Error getting Dacon competition period: {e}")
        return None


def get_dacon_competitions():
    """Dacon 웹사이트를 크롤링하여 현재 진행 중인 대회 정보를 가져오는 함수.

    Returns:
        list: Dacon 대회 정보 리스트. 각 대회는 딕셔너리 형태로 저장
              (platform, name, keywords, url, period 포함)

    Raises:
        Exception: 웹 크롤링 중 오류 발생 시
    """
    base_url = "https://dacon.io"
    main_url = "https://dacon.io/competitions"
    
    try:
        response = requests.get(main_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        competitions = soup.find_all('div', class_='comp')
        active_competitions = []
        
        for comp in competitions:
            status_div = comp.find('div', class_='dday')
            if status_div and '참가신청중' in status_div.text:
                name = comp.find('p', class_='name ellipsis').text.strip()
                keywords = comp.find(
                    'p', class_='info2 ellipsis keyword'
                ).text.strip()
                link_tag = comp.find('a')
                relative_link = link_tag.get('href')
                full_link = urljoin(base_url, relative_link)
                schedule_url = full_link.rstrip('/') + '/schedule'
                period = get_competition_period(schedule_url)
                
                competition_info = {
                    'platform': 'Dacon',
                    'name': name,
                    'keywords': keywords,
                    'url': full_link,
                    'period': period
                }
                active_competitions.append(competition_info)
                logger.info(f"Found Dacon competition: {name}")
        
        return active_competitions
    except Exception as e:
        logger.error(f"Error getting Dacon competitions: {e}")
        return []


def format_slack_message(competition):
    """대회 정보를 Slack 메시지 형식으로 포맷팅하는 함수.

    Args:
        competition (dict): 대회 정보 딕셔너리

    Returns:
        dict: Slack Block Kit 형식의 메시지 구조
    """
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🏆 새로운 {competition['platform']} 대회: {competition['name']}"
            }
        }
    ]
    
    if competition['platform'] == 'Kaggle':
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*설명*: {competition.get('description', '설명 없음')[:300]}..."
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*카테고리*: {competition.get('category', '없음')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*상금*: {competition.get('reward', '없음')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*마감일*: {competition.get('deadline', '없음')}"
                    }
                ]
            }
        ])
    else:  # Dacon
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*키워드*: {competition.get('keywords', '없음')}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*기간*: {competition.get('period', '없음')}"
                }
            }
        ])
    
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "대회 페이지 방문"
                },
                "url": competition.get('url', '')
            }
        ]
    })
    
    return {"blocks": blocks}


def send_slack_notification(competition):
    """대회 정보를 Slack 채널로 전송하는 함수.

    Args:
        competition (dict): 전송할 대회 정보 딕셔너리

    Returns:
        bool: 메시지 전송 성공 여부

    Raises:
        SlackApiError: Slack API 호출 중 오류 발생 시
    """
    try:
        message = format_slack_message(competition)
        response = slack_client.chat_postMessage(
            channel=SLACK_CHANNEL,
            blocks=message["blocks"],
            text=f"새로운 {competition['platform']} 대회: {competition['name']}"
        )
        logger.info(
            f"Slack message sent for {competition['platform']} "
            f"competition: {competition['name']}"
        )
        return True
    except SlackApiError as e:
        logger.error(f"Error sending Slack message: {e.response['error']}")
        return False


def send_no_competition_notification():
    """새로운 대회가 없을 때 Slack 채널로 알림을 전송하는 함수.

    Returns:
        bool: 메시지 전송 성공 여부

    Raises:
        SlackApiError: Slack API 호출 중 오류 발생 시
    """
    try:
        message = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "🔍 *대회 알림 업데이트*\n"
                            "현재 새로운 대회가 없습니다. "
                            "다음 업데이트를 기다려주세요!"
                        )
                    }
                }
            ]
        }
        response = slack_client.chat_postMessage(
            channel=SLACK_CHANNEL,
            blocks=message["blocks"],
            text="새로운 대회가 없습니다."
        )
        logger.info("No competition notification sent")
        return True
    except SlackApiError as e:
        logger.error(f"Error sending Slack message: {e.response['error']}")
        return False


def check_new_competitions():
    """새로운 대회를 확인하고 알림을 보내는 메인 함수.
    
    1. 이전 데이터를 로드
    2. 현재 Kaggle과 Dacon의 대회 정보를 가져옴
    3. 새로운 대회가 있는지 확인
    4. 결과를 저장하고 알림을 전송

    Returns:
        None
    """
    logger.info("Checking for new competitions...")
    
    # 1. 이전 데이터 로드
    previous_competitions = load_competition_data()
    
    # 2. 현재 대회 정보 가져오기
    current_kaggle = get_kaggle_competitions()
    current_dacon = get_dacon_competitions()
    current_competitions = current_kaggle + current_dacon
    
    # 3. 새로운 대회 찾기
    new_competitions = find_new_competitions(current_competitions, previous_competitions)
    
    # 4. 현재 데이터 저장 (기존 데이터 업데이트)
    save_competition_data(current_competitions)
    
    # 새로운 대회 여부와 관계없이 항상 알림 보내기
    if new_competitions:
        logger.info(f"Found {len(new_competitions)} new competitions")
        for comp in new_competitions:
            send_slack_notification(comp)
    else:
        logger.info("No new competitions found")
        send_no_competition_notification()


def clean_competition_data():
    """기존 대회 데이터의 URL 중복 문제를 해결하는 함수.
    
    Returns:
        None
    """
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                competitions = json.load(f)
            
            # URL 중복 수정
            for comp in competitions:
                if 'url' in comp and 'https://www.kaggle.com/competitions/https://www.kaggle.com/competitions/' in comp['url']:
                    comp['url'] = comp['url'].replace('https://www.kaggle.com/competitions/https://www.kaggle.com/competitions/', 'https://www.kaggle.com/competitions/')
            
            # 수정된 데이터 저장
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(competitions, f, ensure_ascii=False, indent=2)
            
            logger.info("Competition data cleaned successfully")
    except Exception as e:
        logger.error(f"Error cleaning competition data: {e}")


def main():
    """프로그램의 메인 실행 함수.
    
    1. 스케줄러를 설정하여 2분 간격으로 실행 (주말 제외)
    2. 프로그램 시작 시 한 번 실행
    3. 무한 루프로 스케줄러 실행
    """
    logger.info("Competition notification bot started")
    
    # 기존 데이터 정리
    clean_competition_data()
    
    # 스케줄러 설정 (2분 간격으로 실행, 주말 제외)
    schedule.every(2).minutes.do(check_new_competitions)
    
    logger.info("Scheduler set to run every 2 minutes on weekdays")
    
    # 스케줄러 실행
    while True:
        # 주말이 아닐 때만 스케줄러 실행
        if datetime.now().weekday() < 5:  # 0-4는 월요일부터 금요일
            schedule.run_pending()
        time.sleep(60)  # 1분마다 체크



if __name__ == "__main__":
    main()

'''
def main():
    """프로그램의 메인 실행 함수.
    
    1. 스케줄러를 설정하여 매일 오전 10시 30분에 실행 (주말 제외)
    2. 프로그램 시작 시 한 번 실행
    3. 무한 루프로 스케줄러 실행
    """
    logger.info("Competition notification bot started")
    
    # 기존 데이터 정리
    clean_competition_data()
    
    # 스케줄러 설정 (매일 오후 12시 30분에 실행, 주말 제외
    schedule.every().day.at("12:30").do(check_new_competitions)
    
    logger.info("Scheduler set to run at 12:30 AM on weekdays")
    
    # 스케줄러 실행
    while True:
        # 주말이 아닐 때만 스케줄러 실행
        if datetime.now().weekday() < 5:  # 0-4는 월요일부터 금요일
            schedule.run_pending()
        time.sleep(60)  # 1분마다 체크


        send_slack_notification()
'''