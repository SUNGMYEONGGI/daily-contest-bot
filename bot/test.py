#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
대회 알림 봇의 로컬 테스트를 위한 스크립트
"""

import os
import json
import shutil
from datetime import datetime
from main import (
    get_kaggle_competitions,
    get_dacon_competitions,
    send_slack_notification,
    clean_competition_data,
    get_new_competitions,
    logger,
    DATA_FILE as MAIN_DATA_FILE,
    DATA_DIR as MAIN_DATA_DIR
)

# 테스트 데이터 디렉토리 설정
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "test")
TEST_DATA_FILE = os.path.join(TEST_DATA_DIR, "competition_data.json")
TEST_BACKUP_FILE = os.path.join(TEST_DATA_DIR, "competition_data.json.backup")

def setup_test_environment():
    """
    테스트 환경을 설정하는 함수
    
    1. 테스트 데이터 디렉토리 생성
    2. 메인 데이터 파일이 있다면 테스트 디렉토리로 복사
    """
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    
    # 메인 데이터 파일이 있으면 테스트 디렉토리로 복사
    if os.path.exists(MAIN_DATA_FILE):
        shutil.copy2(MAIN_DATA_FILE, TEST_DATA_FILE)
        logger.info(f"Copied main data file to test directory: {TEST_DATA_FILE}")

def test_competition_bot():
    """
    대회 알림 봇의 기능을 테스트하는 함수
    
    1. competition_data.json 파일 백업
    2. 각 플랫폼별 대회 정보 크롤링 테스트
    3. 새로운 대회 감지 및 알림 전송 테스트
    4. 변경사항이 있는 경우 결과 출력
    5. 백업 파일 복구 (테스트 완료 후 원래 상태로 복원)
    """
    logger.info("Starting competition bot test")
    
    # competition_data.json 백업
    if os.path.exists(TEST_DATA_FILE):
        with open(TEST_DATA_FILE, "r", encoding="utf-8") as f:
            original_data = f.read()
        with open(TEST_BACKUP_FILE, "w", encoding="utf-8") as f:
            f.write(original_data)
        logger.info("Original competition data backed up")
    
    try:
        # 기존 데이터 정리
        clean_competition_data()
        
        # 각 플랫폼별 대회 정보 크롤링 테스트
        logger.info("Testing Kaggle competitions crawling...")
        kaggle_competitions = get_kaggle_competitions()
        logger.info(f"Found {len(kaggle_competitions)} Kaggle competitions")
        
        logger.info("Testing Dacon competitions crawling...")
        dacon_competitions = get_dacon_competitions()
        logger.info(f"Found {len(dacon_competitions)} Dacon competitions")
        
        # 전체 대회 목록 생성
        current_competitions = []
        current_competitions.extend(kaggle_competitions)
        current_competitions.extend(dacon_competitions)
        
        # 저장된 대회 정보 로드
        if os.path.exists(TEST_DATA_FILE):
            with open(TEST_DATA_FILE, "r", encoding="utf-8") as f:
                saved_competitions = json.load(f)
        else:
            saved_competitions = []
        
        # 새로운 대회 찾기
        new_competitions = get_new_competitions(current_competitions, saved_competitions)
        
        # 새로운 대회 알림 테스트
        if new_competitions:
            logger.info(f"Found {len(new_competitions)} new competitions:")
            for comp in new_competitions:
                logger.info(f"- [{comp['platform']}] {comp['name']}")
                # 알림 전송 테스트
                send_slack_notification(comp)
        else:
            logger.info("No new competitions found")
        
        # 현재 대회 정보 저장
        with open(TEST_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(current_competitions, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        raise
    
    finally:
        # 백업 파일이 있으면 복구
        if os.path.exists(TEST_BACKUP_FILE):
            with open(TEST_BACKUP_FILE, "r", encoding="utf-8") as f:
                original_data = f.read()
            with open(TEST_DATA_FILE, "w", encoding="utf-8") as f:
                f.write(original_data)
            os.remove(TEST_BACKUP_FILE)
            logger.info("Original competition data restored")

def main():
    """
    테스트 실행을 위한 메인 함수
    """
    # 환경 변수 확인
    required_vars = ['SLACK_TOKEN', 'SLACK_CHANNEL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set them in .env file or export them before running the test")
        return
    
    # Kaggle API 자격 증명 파일 확인
    kaggle_path = os.path.expanduser("~/.kaggle/kaggle.json")
    if not os.path.exists(kaggle_path):
        logger.error(f"Kaggle credentials not found at {kaggle_path}")
        logger.error("Please set up Kaggle API credentials before running the test")
        return
    
    logger.info("Starting test run...")
    logger.info(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        setup_test_environment()
        test_competition_bot()
        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {e}")

if __name__ == "__main__":
    main() 