import re
import json
import csv
import pandas as pd
from datetime import date, timedelta, datetime
import configparser
import requests
from bs4 import BeautifulSoup

# NOTE DO NOT INCLUDE MAP IDS IN CONFIG INI THAT WERE MADE THE DAY OF RUNNING SCRIPT DUE TO HOW DATES ARE HANDLED ON ATLAS

class AtlasStats:
	def __init__(self):
		# Import config file information
		config = configparser.ConfigParser()
		config.read('config.ini')

		self.cookie = {'PHPSESSID': config['Cookies']['PHPSESSID']}    # Uses Atlas cookie if you are admin/moderator to see hidden level information
		self.level_count_start = config['Level ID Range']['START']        # Atlas ID for starting count
		self.level_count_end = config['Level ID Range']['END']            # Atlas ID for ending count

		# LEVEL INFORMATION
		self.level_title = 'N/A'
		self.level_author = 'N/A'
		self.level_date = 'N/A'
		self.level_status = None
		# LEVEL LIKE RATINGS
		self.level_likes_score = 'N/A'
		self.level_likes_count = 'N/A'
		self.level_likes_total_score = 'N/A'
		# LEVEL DIFFICULTY RATINGS
		self.level_difficulty_score = 'N/A'
		self.level_difficulty_count = 'N/A'
		self.level_difficulty_total_score = 'N/A'
		# LEVEL TAGS
		self.level_tag_list = 'N/A'

		# UTILITIES
		self.level_id = None
		self.level_data = {}
		self.html = None
		self.admin_cookie = None
		self.dk_level_data = {}
		self.ordered_dk_level_data = {}


	def run(self):
		"""Controller"""
		# Downloads all level data from dustkid and stores it in a JSON
		self.download_dk_data()
		self.reorder_dk_data()
		self.cookie_check()
		
		config = configparser.ConfigParser()
		config.read('config.ini')

		for self.level_id in range(int(config['Level ID Range']['START']), int(config['Level ID Range']['END']) + 1):
			print(f'level {self.level_id}')
			self.get_html()
			self.level_status_check()
			if self.level_status == 'UNPUBLISHED':
				continue
			self.grab_atlas_level_data()
			self.add_dustkid_data()
			self.build_data()
			self.reset()

		self.dump_data()

	def reset(self):
		# LEVEL INFORMATION
		self.level_title = 'N/A'
		self.level_author = 'N/A'
		self.level_date = 'N/A'
		self.level_status = None
		# LEVEL LIKE RATINGS
		self.level_likes_score = 'N/A'
		self.level_likes_count = 'N/A'
		self.level_likes_total_score = 'N/A'
		# LEVEL DIFFICULTY RATINGS
		self.level_difficulty_score = 'N/A'
		self.level_difficulty_count = 'N/A'
		self.level_difficulty_total_score = 'N/A'
		# LEVEL TAGS
		self.level_tag_list = 'N/A'

	def download_dk_data(self):
		"""Grabs all levels from dustkid.com/levels.php by cycling through each page. Can only show 1024 levels at a time"""
		prev = False
		self.dk_level_data = {}

		while True:
			url = 'https://dustkid.com/levels.php?count=1024&prev='          
			if prev:                                                         # Pulls the next level in the list
				dk_level_data_section = requests.get(url + prev).json()
				prev = dk_level_data_section['next']
				self.dk_level_data.update(dk_level_data_section['levels'])         # Inserts next page into the dictionary
			elif prev is False:                                              
				dk_level_data_section = requests.get(url).json()
				prev = dk_level_data_section['next']                            
				self.dk_level_data = dk_level_data_section['levels']
			elif prev is None:                                               # No more levels in list
				break

	def reorder_dk_data(self):
		"""Reorders Dustkid Level data by Atlas ID for easy comparison with atlas data"""
		temp_dk_level_data = self.dk_level_data.copy()
		for key, value in temp_dk_level_data.items():
			atlas_id = value['atlas_id']
			if atlas_id == 0:                                            # Deletes "bad data" levels, those with atlas_id: 0
				del self.dk_level_data[key]
			else:                                                        # Sets the Atlas ID to be the Key
				del value['atlas_id']
				self.ordered_dk_level_data[atlas_id] = value             # Note: author: "" Means its an unpublished level

	def cookie_check(self):
		"""Checks if the given cookie is valid or blank"""

		if self.cookie.get('PHPSESSID'):                                
					admin_request = requests.get('https://atlas.dustforce.com/admin/moderate', cookies=self.cookie)  
					admin_html = BeautifulSoup(admin_request.content, 'html.parser')
					
					if admin_html.find('li', {'class': 'qa-nav-main-item qa-nav-main-admin'}):
						self.admin_cookie = True
					else:
						exit('Remove cookie from config.ini file or use an admin/moderator cookie')

		else:
			self.admin_cookie = False
	
	def get_html(self):
		request = requests.get(f'https://atlas.dustforce.com/{self.level_id}', cookies=self.cookie)
		self.html = BeautifulSoup(request.content, 'html.parser')

	def level_status_check(self):
		"""Checks if the level is published/hidden/unpublsished"""

		if self.admin_cookie:
			if self.html.find('meta', {'property': 'og:title'}).get('content') == 'Atlas - the Dustforce map sharing server':
				self.level_status = 'UNPUBLISHED'
			elif self.html.find('div', {'class': 'qa-q-view-buttons'}).find('input', {'name': 'q_dodelete'}): # Only on admin-view of hidden levels
				self.level_status = 'HIDDEN'
			else:
				self.level_status = 'VISIBLE'

		else:
			if self.html.find('meta', {'property': 'og:title'}).get('content') == ' - a Dustforce map':
				self.level_status = 'HIDDEN'
			elif self.html.find('meta', {'property': 'og:title'}).get('content') == 'Atlas - the Dustforce map sharing server':
				self.level_status = 'UNPUBLISHED'
			else:
				self.level_status = 'VISIBLE'

	def grab_atlas_level_data(self):
		"""Grabs Level Data"""
		### ADMIN ###
		if self.admin_cookie and (self.level_status == 'VISIBLE' or self.level_status == 'HIDDEN'):
			level_info = self.html.find('div', {'class': 'map-info-stats'})                       # Grabs rating information + author html
			tag_info = self.html.find('div', {'class': 'tag-area'})                               # Grabs tag information html

			# LEVEL INFORMATION
			self.level_title = re.findall(r'(.*?)\s+-', self.html.find('title').text)[0]                       # Grabs level title from title tag
			self.level_author = level_info.find_all('div', {'class': 'pull-left'})[1].find('a').text           # Grabs author from div-class tag
			if not self.level_author:
				self.level_author = 'N/A'                                                                      # This can only happen if acc deleted
			self.level_date = self.clean_date(level_info.find_all('div', {'class': 'pull-left'})[1].find_all('span')[1].text)   # Grabs raw level date
			

			# RATING INFORMTION
			level_ratings = level_info.find_all('span', id=True)                                   # Finds span tag and returns like/difficulty list

			level_likes = level_ratings[0].get('class')                                            # Level Likes are stored dynamically
			self.level_likes_score = int(re.findall(r'\d+', level_likes[3])[0])                    # The current like score of the level
			self.level_likes_count = int(re.findall(r'\d+', level_likes[6])[0])                    # Total number of like votes
			self.level_likes_total_score = int(re.findall(r'\d+', level_likes[7])[0])              # All scores added together, the "total" score

			level_difficulty = level_ratings[1].get('class')                                       # Level Difficulty are stored dynamically
			self.level_difficulty_score = int(re.findall(r'\d+', level_difficulty[3])[0])          # The current difficulty score of the level
			self.level_difficulty_count = int(re.findall(r'\d+', level_difficulty[6])[0])          # Total number of difficulty votes
			self.level_difficulty_total_score = int(re.findall(r'\d+', level_difficulty[7])[0])    # All scores added together, the "total" score

			# TAG INFORMATION
			self.level_tag_list = [tag.text for tag in [tag_raw for tag_raw in tag_info.find_all('a')]]  # Grabs a list of the tags on a given level
			
		### NOT ADMIN ###
		if not self.admin_cookie and self.level_status == 'VISIBLE':
			level_info = self.html.find('div', {'class': 'map-info-stats'})                        # Grabs rating information + author html
			tag_info = self.html.find('div', {'class': 'tag-area'})                                # Grabs tag information html

			# LEVEL INFORMATION
			self.level_title = re.findall(r'(.*?)\s+-', self.html.find('title').text)[0]                       # Grabs level title from title tag
			self.level_author = level_info.find_all('div', {'class': 'pull-left'})[1].find('a').text           # Grabs author from div-class tag
			if not self.level_author:
				self.level_author = 'N/A'                                                                      # This can only happen if acc deleted
			self.level_date = self.clean_date(level_info.find_all('div', {'class': 'pull-left'})[1].find_all('span')[1].text)  # Grabs level date

			# RATING INFORMTION
			level_ratings = level_info.find_all('span', id=True)                                   # Finds span tag and returns like/difficulty list

			level_likes = level_ratings[0].get('class')                                            # Level Likes are stored dynamically
			self.level_likes_score = int(re.findall(r'\d+', level_likes[3])[0])                    # The current like score of the level
			self.level_likes_count = int(re.findall(r'\d+', level_likes[6])[0])                    # Total number of like votes
			self.level_likes_total_score = int(re.findall(r'\d+', level_likes[7])[0])              # All scores added together, the "total" score

			level_difficulty = level_ratings[1].get('class')                                       # Level Difficulty are stored dynamically
			self.level_difficulty_score = int(re.findall(r'\d+', level_difficulty[3])[0])          # The current difficulty score of the level
			self.level_difficulty_count = int(re.findall(r'\d+', level_difficulty[6])[0])          # Total number of difficulty votes
			self.level_difficulty_total_score = int(re.findall(r'\d+', level_difficulty[7])[0])    # All scores added together, the "total" score

			# TAG INFORMATION
			self.level_tag_list = [tag.text for tag in [tag_raw for tag_raw in tag_info.find_all('a')]]  # Grabs a list of the tags on a given level

	def clean_date(self, level_date):
		"""Creates a clean date due to how Atlas formats dates of maps"""
		if "days ago" in level_date:                                                               # Created in the last week
			level_date = level_date.replace('created', '').replace('days ago', '').strip()         # Cleans up words
			return (date.today() - timedelta(days=int(level_date))).strftime('%Y-%m-%d')           # Subtracts number from todays date and formats
		if "day ago" in level_date:                                                                # Created in Yesterday
			level_date = level_date.replace('created', '').replace('day ago', '').strip()          # Cleans up words
			return (date.today() - timedelta(days=int(level_date))).strftime('%Y-%m-%d')           # Subtracts number from todays date and formats
		else:
			if not "," in level_date:                                                              # Created in the current year
				level_date = level_date.replace('created', '').strip()                             # Cleans up words
				return (datetime.strptime(level_date + " 2025", "%b %d %Y").strftime('%Y-%m-%d'))  # Converts standerized "Apr/Mar" and adds year
			else:                                                                                  # Created in previous years
				level_date = level_date.replace('created', '').replace(',', '').strip()            # Cleans up words
				return datetime.strptime(level_date, "%b %d %Y").strftime('%Y-%m-%d')              # Converts standerized "Apr/Mar" and formats

	def add_dustkid_data(self): 
		"""Only used if no admin cookie"""
		if not self.admin_cookie and (self.level_status == 'HIDDEN' or self.level_status == 'UNPUBLISHED'):
			self.level_title = self.ordered_dk_level_data[self.level_id]['name']

			if self.ordered_dk_level_data[self.level_id]['author']:
				self.level_author = self.ordered_dk_level_data[self.level_id]['author']
			else:
				self.level_author = 'N/A'


	def build_data(self):
		self.level_data[self.level_id] = {
			'LEVEL ID': self.level_id,
			'LEVEL NAME': self.level_title,
			'AUTHOR': self.level_author,
			'DATE': self.level_date,
			'LEVEL STATUS': self.level_status,
			'HEART SCORE': self.level_likes_score,
			'HEART TOTAL': self.level_likes_count, 
			'HEART TOTAL SCORE': self.level_likes_total_score,
			'DIFFICULTY SCORE': self.level_difficulty_score,
			'DIFFICULTY TOTAL': self.level_difficulty_count,
			'DIFFICULTY TOTAL SCORE': self.level_difficulty_total_score,
			'TAGS': self.level_tag_list
		}

	def dump_data(self):
		# Creates a JSON File
		with open('atlas_data.json', 'w') as f:
			json.dump(self.level_data, f, indent=3)
		
		# Formts CSV to just include Atlas Map VALUES, easy to import into excel
		with open('atlas_data.csv', 'w', newline='', encoding='utf-8') as csvfile:
			writer = csv.writer(csvfile)
			for level_id in self.level_data.values():
				writer.writerow(level_id.values())

x = AtlasStats()
x.run()