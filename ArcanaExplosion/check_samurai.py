#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from engine import cards

cards.apply_skin('samurai')
print('=== 敵キャラクターカード（絵札） ===')
for suit in ['H','D','C','S']:
  for rank in ['J','Q','K','A']:
    key = suit + rank
    if key in cards.FACE_ABILITIES:
      name = cards.FACE_ENEMY_NAMES.get(key, cards.FACE_ABILITIES[key]['name'])
      print('{}: {}'.format(key, name))
print()
print('=== 神軍降臨（豊臣方） ===')
for key in ['SJ','SQ','SK','HJ','HQ','HK','DJ','DQ','DK']:
  print('{}: {}'.format(key, cards.GOD_ARMY_NAMES.get(key, '?')))
print()
print('=== 魔神軍降臨（徳川方） ===')
for key in ['S10','S9','S8','D10','D9','D8']:
  print('{}: {}'.format(key, cards.DEMON_ARMY_NAMES.get(key, '?')))
