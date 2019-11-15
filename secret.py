from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import pandas as pd
import time
from tqdm import tqdm
import random
import sys
import threading

driver = webdriver.Chrome("/Users/igor/Downloads/chromedriver")

username = 'agoodusernameisnotenough'
password = 'test1234'
# user_id = 'didima_feggaria'
user_id = 'igor__sp'
done = False

def main():
    login(username, password, user_id)

    followers_count = getUsersCount('followers')
    followers_list = getUsersList(followers_count, 'followers')

    print('Actual number of followers:' + str(followers_count))
    print('Number of found followers:' + str(len(followers_list)))

    close_modal_button = driver.find_element_by_xpath('/html/body/div[3]/div/div[1]/div/div[2]/button')
    close_modal_button.click()

    following_count = getUsersCount('following')
    following_list = getUsersList(following_count, 'following')

    print('Actual number of following:' + str(following_count))
    print('Number of found following:' + str(len(following_list)))

    s = set(followers_list)
    not_followers = [x for x in following_list if x not in s]

    print('Count of not followers: ' + str(len(not_followers)))
    print(not_followers)

    driver.close()

def login(username, password, user_id):
    driver.get('https://www.instagram.com/accounts/login/?source=auth_switcher')
    time.sleep(3)
    write_username = driver.find_element_by_xpath('//html/body/span/section/main/div/article/div/div[1]/div/form/div[2]/div/label/input').send_keys(username)
    write_password = driver.find_element_by_xpath('/html/body/span/section/main/div/article/div/div[1]/div/form/div[3]/div/label/input')
    write_password.send_keys(password)
    write_password.send_keys(Keys.ENTER)
    time.sleep(2)
    driver.get('https://www.instagram.com/' + user_id)
    time.sleep(2)

def getUsersCount(target):
    if target == 'followers':
        users_count=int(driver.find_element_by_xpath("//li[2]/a/span").text) 
    else:
        users_count=int(driver.find_element_by_xpath("//li[3]/a/span").text) 
    
    return users_count

def getUsersList(followers_count, target):
    global done
    #find users count in user page and click
    if target == "followers":
        users_count_button = driver.find_element_by_xpath('/html/body/span/section/main/div/header/section/ul/li[2]/a')
    else:
        users_count_button = driver.find_element_by_xpath('/html/body/span/section/main/div/header/section/ul/li[3]/a')

    users_count_button.click()
    time.sleep(1)

    #find followers pop up
    dialog = driver.find_element_by_xpath('/html/body/div[3]/div/div[2]')
    time.sleep(1)

    #scroll once for a random ammount to prevent going to suggestions
    driver.execute_script("arguments[0].scrollTop = 300", dialog)

    #scroll through followers to go to the end of the list 
    print('Scrolling through followers\' scroll box:')
    for i in tqdm(range(int(followers_count / 10))): #it is divided by 10 because each iteration scrolls through 12 followers
        time.sleep(random.randint(500,1000)/1000)
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", dialog)

    sys.stdout.write('Searching for users\' divs ')
    # start the spinner in a separate thread
    spin_thread = threading.Thread(target=spin_cursor)
    spin_thread.start()

    page_source = driver.page_source
    domBS=BeautifulSoup(page_source, "lxml") #BS stands for Beautiful Soup !!!

    followersList = []

    followersDivsBS = domBS.find_all("div", class_="d7ByH")

    # tell the spinner to stop, and wait for it to do so;
    # this will clear the last cursor before the program moves on
    done = True
    spin_thread.join()

    with tqdm(total=len(followersDivsBS)) as pbar:
        for followerDivBS in followersDivsBS:
            for a in followerDivBS.find_all('a', href = True):
                followersList.append(a['href'][1:-1]) #Getting rid of the slash at the start and the end of the instagram id 
            pbar.update(1)
        pbar.close()

    return followersList

def spin_cursor():
    while True:
        for cursor in '|/-\\':
            sys.stdout.write(cursor)
            sys.stdout.flush()
            time.sleep(0.1) # adjust this to change the speed
            sys.stdout.write('\b')
            if done:
                return


if __name__ == '__main__':
    main()