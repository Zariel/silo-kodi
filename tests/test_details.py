from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin.video.silo/resources/lib'))
from silo.details import detail_labels


class Details(unittest.TestCase):
    def test_series_facts_and_people(self):
        labels = detail_labels({
            'type': 'series', 'year': 2020, 'content_rating': 'TV-14',
            'genres': ['Comedy'], 'show_status': 'returning',
            'networks': ['Network'], 'crew': [{'job': 'Creator', 'name': 'Alex'}],
            'cast': [{'name': 'Sam'}, {'name': 'Jo'}],
        }, [{'episode_count': 4}, {'episode_count': 6}])
        self.assertEqual(labels['facts'], 'Series  •  2020  •  TV-14  •  2 seasons  •  10 episodes  •  Returning  •  Comedy')
        self.assertEqual(labels['credits'], 'Created by Alex  ·  Cast: Sam, Jo')
        self.assertEqual(labels['format'], 'Network')

    def test_ratings_preserve_server_scale_and_order(self):
        data = {'ratings': [{'name': 'Critics', 'display': '91%'}, {'name': 'TMDB', 'display': '8.3'}],
                'rating_imdb': 7.0}
        self.assertEqual(detail_labels(data, [])['ratings'], 'Critics 91%  •  TMDB 8.3')
        data['ratings'] = []
        self.assertEqual(detail_labels(data, [])['ratings'], '')
        del data['ratings']
        self.assertEqual(detail_labels(data, [])['ratings'], 'IMDb 7.0')

    def test_optional_fields_and_source_formats(self):
        data = {'type': 'episode', 'season_number': 0, 'episode_number': 1,
                'runtime': 42, 'genres': None, 'ratings': None, 'cast': None, 'crew': None,
                'overlay_summary': {'resolution': '4K', 'hdr': 'Dolby Vision', 'audio': 'TrueHD'}}
        labels = detail_labels(data, [])
        self.assertEqual(labels['facts'], 'Episode  •  42 min  •  S0 E1')
        self.assertEqual(labels['format'], '4K  •  Dolby Vision  •  TrueHD')
        self.assertEqual(labels['credits'], '')
        self.assertEqual(labels['ratings'], '')

    def test_season_counts_only_its_episodes(self):
        labels = detail_labels({'type': 'series', 'season_count': 23, 'episode_count': 207}, [{}, {}], season=True)
        self.assertEqual(labels['facts'], 'Series  •  2 episodes')
