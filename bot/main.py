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
from pathlib import Path
import re

# Third-party imports
import schedule
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from kaggle.api.kaggle_api_extended import KaggleApi


# 상수 정의
SLACK_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#contest-notify-bot")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "main")  # 메인 데이터 디렉토리
DATA_FILE = os.path.join(DATA_DIR, "competition_data.json")
LOG_FILE = os.path.join(DATA_DIR, "competition_bot.log")

# 로깅 설정
os.makedirs(DATA_DIR, exist_ok=True)  # 데이터 디렉토리 생성
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 환경 변수 로드
load_dotenv()

# Slack 클라이언트 초기화
slack_client = WebClient(token=SLACK_TOKEN)


def save_competition_data(data):
    """대회 정보를 파일로 저장하는 함수.

    Args:
        data (list): 저장할 대회 정보 리스트
    """
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Competition data saved successfully")
    except Exception as e:
        logger.error(f"Error saving competition data: {e}")


def load_competition_data():
    """저장된 대회 정보를 불러오는 함수.

    Returns:
        list: 저장된 대회 정보 리스트
    """
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading competition data: {e}")
            return []
    return []


def get_new_competitions(current_competitions, saved_competitions):
    """새로운 대회를 찾는 함수.

    Args:
        current_competitions (list): 현재 수집된 대회 정보 리스트
        saved_competitions (list): 저장된 대회 정보 리스트

    Returns:
        list: 새로 발견된 대회 정보 리스트
    """
    saved_urls = {comp['url'] for comp in saved_competitions}
    new_urls = {comp['url'] for comp in current_competitions} - saved_urls
    return [comp for comp in current_competitions if comp['url'] in new_urls]


def get_kaggle_competitions():
    """Kaggle API를 사용하여 현재 진행 중인 대회 정보를 가져오는 함수.

    Returns:
        list: Kaggle 대회 정보 리스트. 각 대회는 딕셔너리 형태로 저장
              (platform, name, description, url, deadline, category, reward, image_url 포함)

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
                
                # 웹 크롤링으로 이미지 URL 추출
                try:
                    response = requests.get(url)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 이미지 URL 찾기 (여러 패턴 시도)
                    image_url = None
                    
                    # 1. OpenGraph 이미지 태그 확인
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        image_url = og_image.get('content')
                    
                    # 2. 대회 로고 이미지 찾기
                    if not image_url:
                        logo_img = soup.find('img', class_='competition-logo')
                        if logo_img and logo_img.get('src'):
                            image_url = logo_img.get('src')
                    
                    # 3. 대회 헤더 이미지 찾기
                    if not image_url:
                        header_img = soup.find('img', class_='competition-header')
                        if header_img and header_img.get('src'):
                            image_url = header_img.get('src')
                    
                    # 4. data-src 속성 확인
                    if not image_url:
                        img_with_data_src = soup.find('img', attrs={'data-src': True})
                        if img_with_data_src:
                            image_url = img_with_data_src.get('data-src')
                    
                    # URL이 상대 경로인 경우 절대 경로로 변환
                    if image_url and not image_url.startswith(('http://', 'https://')):
                        image_url = urljoin('https://www.kaggle.com', image_url)
                        
                except Exception as e:
                    logger.error(f"Error scraping competition page for images: {e}")
                    image_url = None
                
                competition_list.append({
                    'platform': 'Kaggle',
                    'name': comp.title,
                    'description': comp.description,
                    'url': url,
                    'deadline': comp.deadline.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    'category': comp.category,
                    'reward': f"${comp.reward}",
                    'image_url': image_url
                })
                logger.info(f"Found Kaggle competition: {comp.title}")
                if image_url:
                    logger.info(f"Found image for competition: {comp.title}")
                else:
                    logger.warning(f"No image found for competition: {comp.title}")
        
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
            # 기간 텍스트에서 앞부분 제거
            period = period_text.replace('- 대회 기간 : ', '').strip()
            
            # 시간 정보 제거 (정규 표현식 사용)
            cleaned_period = re.sub(r'\d{1,2}:\d{2}', '', period)
            
            # "~" 기준으로 분리하여 시작일과 종료일 정리
            parts = cleaned_period.split('~')
            if len(parts) == 2:
                start_date = parts[0].strip()
                end_date = parts[1].strip()
                # 앞뒤 공백 정리 후 다시 결합
                return f"{start_date} ~ {end_date}"
                
            return cleaned_period
        return "기간 정보를 찾을 수 없습니다."
    except Exception as e:
        logger.error(f"Error getting Dacon competition period: {e}")
        return None


def get_dacon_competitions():
    """Dacon 웹사이트를 크롤링하여 현재 진행 중인 대회 정보를 가져오는 함수.

    Returns:
        list: Dacon 대회 정보 리스트. 각 대회는 딕셔너리 형태로 저장
              (platform, name, keywords, url, period, image_url 포함)

    Raises:
        Exception: 웹 크롤링 중 오류 발생 시
    """
    base_url = "https://dacon.io"
    main_url = "https://dacon.io/competitions"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(main_url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        competitions = soup.find_all('div', class_='comp')
        active_competitions = []
        
        for comp in competitions:
            try:
                status_div = comp.find('div', class_='dday')
                if status_div and '참가신청중' in status_div.text:
                    # 기본 정보 추출
                    name = comp.find('p', class_='name ellipsis').text.strip()
                    keywords = comp.find(
                        'p', class_='info2 ellipsis keyword'
                    ).text.strip()
                    link_tag = comp.find('a')
                    relative_link = link_tag.get('href')
                    full_link = urljoin(base_url, relative_link)
                    schedule_url = full_link.rstrip('/') + '/schedule'
                    period = get_competition_period(schedule_url)
                    
                    # 이미지 URL 추출
                    image_url = None
                    img_tag = comp.find('img')
                    if img_tag:
                        image_url = img_tag.get('src') or img_tag.get('data-src')
                        if image_url and not image_url.startswith(('http://', 'https://')):
                            image_url = urljoin(base_url, image_url)
                    
                    competition_info = {
                        'platform': 'Dacon',
                        'name': name,
                        'keywords': keywords,
                        'url': full_link,
                        'period': period,
                        'image_url': image_url
                    }
                    active_competitions.append(competition_info)
                    logger.info(f"Found Dacon competition: {name}")
                    if image_url:
                        logger.info(f"Found image for competition: {name}")
                    else:
                        logger.warning(f"No image found for competition: {name}")
            
            except Exception as e:
                logger.error(f"Error processing Dacon competition: {e}")
                continue
        
        if not active_competitions:
            logger.warning("No active competitions found on Dacon website")
        
        return active_competitions
    
    except Exception as e:
        logger.error(f"Error getting Dacon competitions: {e}")
        return []


def format_slack_message(competition):
    """대회 정보를 Slack 메시지 형식으로 변환하는 함수.

    Args:
        competition (dict): 대회 정보

    Returns:
        dict: Slack 메시지 블록
    """
    blocks = []
    
    # 헤더 섹션
    platform_name = "Kaggle" if competition['platform'] == 'Kaggle' else "Dacon"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"🔥 새로운 *{platform_name}* 대회가 열렸어요!"
        }
    })
    
    # 구분선
    blocks.append({
        "type": "divider"
    })
    
    # 대회 정보 섹션
    competition_section = {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*<{competition['url']}|{competition['name']}>*\n"
        }
    }

    if competition['platform'] == 'Kaggle':
        competition_section["text"]["text"] += (
            f"카테고리: {competition.get('category', '없음')}\n"
            f"상금: {competition.get('reward', '없음')}\n"
            f"마감일: {competition.get('deadline', '없음')}"
        )
    else:  # Dacon
        competition_section["text"]["text"] += (
            f"키워드: {competition.get('keywords', '없음')}\n"
            f"상금: {competition.get('reward', '없음')}\n"
            f"기간: {competition.get('period', '없음')}"
        )

    # 이미지가 있는 경우 accessory로 추가
    if competition.get('image_url'):
        competition_section["accessory"] = {
            "type": "image",
            "image_url": competition['image_url'],
            "alt_text": "대회 이미지 썸네일"
        }

    blocks.append(competition_section)

    # 컨텍스트 섹션 추가
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "image",
                "image_url": "https://api.slack.com/img/blocks/bkb_template_images/tripAgentLocationMarker.png",
                "alt_text": "Location Pin Icon"
            },
            {
                "type": "plain_text",
                "emoji": True,
                "text": competition.get('description', '')[:100] if competition['platform'] == 'Kaggle' else competition.get('keywords', '')
            }
        ]
    })
    
    # 구분선
    blocks.append({
        "type": "divider"
    })
    
    # 액션 버튼 추가
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "emoji": True,
                    "text": "같이 할 사람 찾기 👋🏼"
                },
                "url": "https://forms.gle/pjKkvprwGQpGgPTE9",
                "value": "go_to_surveyform"
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "emoji": True,
                    "text": "대회 페이지 방문"
                },
                "url": competition['url'],
                "value": "go_to_competition"
            }
        ]
    })
    
    return blocks


def send_slack_notification(competition):
    """Slack으로 대회 알림을 보내는 함수.

    Args:
        competition (dict): 대회 정보
    """
    try:
        blocks = format_slack_message(competition)
        
        # 디버깅: 블록 구조 출력
        logger.info(f"Sending notification with {len(blocks)} blocks")
        
        response = slack_client.chat_postMessage(
            channel=SLACK_CHANNEL,
            blocks=blocks,
            text=f"New competition: {competition['name']}",  # 폴백 텍스트
            unfurl_links=False,  # 링크 미리보기 비활성화
            unfurl_media=False   # 미디어 미리보기 비활성화
        )
        if response["ok"]:
            logger.info(f"Slack notification sent for: {competition['name']}")
        else:
            logger.error(f"Failed to send Slack notification: {response['error']}")
    except SlackApiError as e:
        logger.error(f"Error sending Slack notification: {e.response['error']}")
        # 추가 디버깅 정보
        if 'blocks' in e.response:
            logger.error(f"Invalid blocks detail: {e.response['blocks']}")
    except Exception as e:
        logger.error(f"Unexpected error sending notification: {str(e)}")


def check_new_competitions():
    """새로운 대회를 확인하고 알림을 보내는 함수."""
    try:
        # 저장된 대회 정보 로드
        saved_competitions = load_competition_data()
        
        # 현재 진행 중인 대회 정보 수집
        current_competitions = []
        current_competitions.extend(get_kaggle_competitions())
        current_competitions.extend(get_dacon_competitions())
        
        if not current_competitions:
            logger.warning("No competitions found")
            return
        
        # 새로운 대회 찾기
        new_competitions = get_new_competitions(current_competitions, saved_competitions)
        
        # 새로운 대회가 있으면 알림 전송
        for comp in new_competitions:
            send_slack_notification(comp)
        
        # 대회 정보 저장
        save_competition_data(current_competitions)
        
        if new_competitions:
            logger.info(f"Found {len(new_competitions)} new competitions")
        else:
            logger.info("No new competitions found")
            
    except Exception as e:
        logger.error(f"Error checking new competitions: {e}")


def clean_competition_data():
    """만료된 대회를 제거하는 함수."""
    try:
        competitions = load_competition_data()
        if not competitions:
            return
        
        current_time = datetime.now()
        cleaned_competitions = []
        
        for comp in competitions:
            # Kaggle 대회의 경우 deadline 확인
            if comp['platform'] == 'Kaggle':
                deadline = datetime.strptime(
                    comp['deadline'],
                    "%Y-%m-%d %H:%M:%S UTC"
                )
                if deadline > current_time:
                    cleaned_competitions.append(comp)
            else:  # Dacon 대회의 경우 모두 포함 (크롤링 시 이미 진행 중인 대회만 수집)
                cleaned_competitions.append(comp)
        
        save_competition_data(cleaned_competitions)
        logger.info("Competition data cleaned")
        
    except Exception as e:
        logger.error(f"Error cleaning competition data: {e}")


def main():
    """메인 함수."""
    logger.info("Competition notification bot started")
    
    # 1분마다 새로운 대회 확인
    schedule.every(1).minutes.do(check_new_competitions)
    
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()