"""Display facts supplied by Silo; never infer playback capability from badges."""


def detail_labels(data, items, season=False):
    kind = data.get('type', '')
    facts = [kind.title()] if kind else []
    for field in ('year', 'content_rating'):
        if data.get(field):
            facts.append(str(data[field]))
    if data.get('runtime'):
        facts.append('{} min'.format(data['runtime']))
    if kind == 'series':
        count = len(items) if season else data.get('season_count') or len(items)
        facts.append('{} {}'.format(count, 'episodes' if season else 'seasons'))
        if not season:
            episodes = data.get('episode_count')
            if episodes is None and items and all(type(item.get('episode_count')) is int for item in items):
                episodes = sum(item['episode_count'] for item in items)
            if episodes is not None:
                facts.append('{} episodes'.format(episodes))
        if data.get('show_status'):
            facts.append(data['show_status'].replace('_', ' ').title())
    if kind == 'episode' and data.get('season_number') is not None and data.get('episode_number') is not None:
        facts.append('S{} E{}'.format(data['season_number'], data['episode_number']))
    facts.extend((data.get('genres') or [])[:3])
    ratings = ['{} {}'.format(rating['name'], rating['display']) for rating in (data.get('ratings') or [])
               if rating.get('name') and rating.get('display')]
    if 'ratings' not in data:
        for field, label in (('rating_imdb', 'IMDb'), ('rating_tmdb', 'TMDB')):
            if data.get(field) is not None:
                ratings.append('{} {}'.format(label, data[field]))
    people = []
    for job, label in (('Creator', 'Created by'), ('Director', 'Directed by')):
        names = list(dict.fromkeys(person['name'] for person in (data.get('crew') or [])
                                  if person.get('job') == job and person.get('name')))
        if names:
            people.append(label + ' ' + ', '.join(names[:3]))
    cast = [person['name'] for person in (data.get('cast') or []) if person.get('name')][:4]
    if cast:
        people.append('Cast: ' + ', '.join(cast))
    production = data.get('networks') or data.get('studios') or []
    overlay = data.get('overlay_summary') or {}
    technical = [str(overlay[key]) for key in ('resolution', 'hdr', 'video_codec', 'audio', 'audio_channels', 'edition')
                 if overlay.get(key)]
    state = data.get('user_state') or {}
    personal = [label for field, label in (('played', 'Watched'), ('is_favorite', 'Favourite'), ('in_watchlist', 'In watchlist'))
                if state.get(field) is True]
    return {
        'facts': '  •  '.join(facts),
        'ratings': '  •  '.join(ratings + personal),
        'credits': '  ·  '.join(people),
        'format': '  •  '.join(list(production[:2]) + technical),
    }
