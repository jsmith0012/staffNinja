"""Anime-themed waiting quotes for job queue status messages.

Every convention needs its downtime between panels — here's how staffNinja
fills the silence while background jobs are processing.
"""

from __future__ import annotations

import random

# ──────────────────────────────────────────────────────────────────────────────
# Anime Wait-Reference Table
# ──────────────────────────────────────────────────────────────────────────────
#
# ┌───┬───────────────────────────┬──────────────────────────────────────────────────────────────────────┬─────────────────────┐
# │ # │ Anime / Source            │ Quote / Reference                                                    │ Context             │
# ├───┼───────────────────────────┼──────────────────────────────────────────────────────────────────────┼─────────────────────┤
# │ 1 │ Naruto                    │ "Believe it! This task is training harder than Naruto waiting for    │ Naruto's years of   │
# │   │                           │  Sasuke to come home."                                               │ patience             │
# │ 2 │ Dragon Ball Z             │ "Charging up like a Spirit Bomb… this one takes a few episodes."     │ Multi-ep power-ups  │
# │ 3 │ One Piece                 │ "Luffy waited 2 years to reunite with his crew. Your job won't take │ Timeskip training   │
# │   │                           │  that long… probably."                                               │                     │
# │ 4 │ Steins;Gate               │ "El Psy Kongroo… the microwave is still running."                   │ Time-travel waiting │
# │ 5 │ Attack on Titan           │ "Waiting behind the walls for this task to break through."           │ Waiting for action  │
# │ 6 │ My Hero Academia          │ "Processing… Plus Ultra! Almost there!"                              │ Going beyond limits │
# │ 7 │ Fullmetal Alchemist       │ "Equivalent Exchange: you submitted a job, now wait for the result." │ Core alchemy law    │
# │ 8 │ Demon Slayer              │ "Breathing steady… Total Concentration while we process this."       │ Focus breathing     │
# │ 9 │ Jujutsu Kaisen            │ "Domain Expansion: Job Queue! Stand by."                             │ Domain Expansion    │
# │10 │ Neon Genesis Evangelion    │ "Get in the queue, Shinji."                                          │ "Get in the robot"  │
# │11 │ Cowboy Bebop               │ "See you, Space Cowboy… when this job finishes."                     │ Iconic end card     │
# │12 │ Sword Art Online           │ "You're stuck in the queue now. Logging out is not an option."       │ Trapped in SAO      │
# │13 │ Re:Zero                    │ "If this fails, we Return by Death and try again."                   │ Subaru's resets     │
# │14 │ Hunter × Hunter            │ "This job is on hiatus… just kidding, it's almost done."             │ Togashi's hiatuses  │
# │15 │ Death Note                 │ "I'll take this job… and process it! 📝"                             │ Kira's planning     │
# │16 │ Mob Psycho 100             │ "Emotional capacity at 99%… task completing soon."                   │ Mob's ???% meter    │
# │17 │ One Punch Man              │ "Could finish this in One Punch… but the queue has rules."           │ Saitama's power     │
# │18 │ Spy × Family               │ "Mission accepted. Handler is processing your request. 🥜"           │ Loid's spy missions │
# │19 │ Chainsaw Man               │ "Pochita, lend me your power to finish this task!"                   │ Denji's contract    │
# │20 │ Bocchi the Rock!            │ "Bocchi is too anxious to process faster… please wait. 🎸"           │ Bocchi's anxiety    │
# │21 │ Gintama                    │ "The job is running. Meanwhile, enjoy some strawberry milk."          │ Gintoki's chill     │
# │22 │ Bleach                     │ "Bankai! …just kidding, still in Shikai. Processing."                │ Power levels        │
# │23 │ Gurren Lagann              │ "Who the hell do you think this queue is?! Row row, fight the powa!" │ Kamina energy       │
# │24 │ Konosuba                   │ "Aqua is 'helping' with this task. Please lower expectations."       │ Aqua being useless  │
# │25 │ Code Geass                 │ "Lelouch commands you: wait for this result!"                        │ Geass commands      │
# │26 │ Fairy Tail                 │ "The power of friendship will complete this task!"                    │ Nakama power        │
# │27 │ Tokyo Ghoul                │ "This task is 1000 minus 7… 993… still counting."                    │ Kaneki's counting   │
# │28 │ Inuyasha                   │ "Sit, boy! The queue will get to you when it gets to you."           │ Kagome's command    │
# │29 │ Sailor Moon                │ "In the name of the Moon, your task will be completed! 🌙"           │ Sailor Moon speech  │
# │30 │ Yu-Gi-Oh!                  │ "You activated my trap card: Queue Position +1."                     │ Trap card moment    │
# └───┴───────────────────────────┴──────────────────────────────────────────────────────────────────────┴─────────────────────┘

ANIME_WAIT_QUOTES: list[dict[str, str]] = [
    {
        "anime": "Naruto",
        "quote": "Believe it! This task is training harder than Naruto waiting for Sasuke to come home.",
    },
    {
        "anime": "Dragon Ball Z",
        "quote": "Charging up like a Spirit Bomb… this one takes a few episodes.",
    },
    {
        "anime": "One Piece",
        "quote": "Luffy waited 2 years to reunite with his crew. Your job won't take that long… probably.",
    },
    {
        "anime": "Steins;Gate",
        "quote": "El Psy Kongroo… the microwave is still running.",
    },
    {
        "anime": "Attack on Titan",
        "quote": "Waiting behind the walls for this task to break through.",
    },
    {
        "anime": "My Hero Academia",
        "quote": "Processing… Plus Ultra! Almost there!",
    },
    {
        "anime": "Fullmetal Alchemist",
        "quote": "Equivalent Exchange: you submitted a job, now wait for the result.",
    },
    {
        "anime": "Demon Slayer",
        "quote": "Breathing steady… Total Concentration while we process this.",
    },
    {
        "anime": "Jujutsu Kaisen",
        "quote": "Domain Expansion: Job Queue! Stand by.",
    },
    {
        "anime": "Neon Genesis Evangelion",
        "quote": "Get in the queue, Shinji.",
    },
    {
        "anime": "Cowboy Bebop",
        "quote": "See you, Space Cowboy… when this job finishes.",
    },
    {
        "anime": "Sword Art Online",
        "quote": "You're stuck in the queue now. Logging out is not an option.",
    },
    {
        "anime": "Re:Zero",
        "quote": "If this fails, we Return by Death and try again.",
    },
    {
        "anime": "Hunter × Hunter",
        "quote": "This job is on hiatus… just kidding, it's almost done.",
    },
    {
        "anime": "Death Note",
        "quote": "I'll take this job… and process it! \U0001f4dd",
    },
    {
        "anime": "Mob Psycho 100",
        "quote": "Emotional capacity at 99%… task completing soon.",
    },
    {
        "anime": "One Punch Man",
        "quote": "Could finish this in One Punch… but the queue has rules.",
    },
    {
        "anime": "Spy × Family",
        "quote": "Mission accepted. Handler is processing your request. \U0001f95c",
    },
    {
        "anime": "Chainsaw Man",
        "quote": "Pochita, lend me your power to finish this task!",
    },
    {
        "anime": "Bocchi the Rock!",
        "quote": "Bocchi is too anxious to process faster… please wait. \U0001f3b8",
    },
    {
        "anime": "Gintama",
        "quote": "The job is running. Meanwhile, enjoy some strawberry milk.",
    },
    {
        "anime": "Bleach",
        "quote": "Bankai! …just kidding, still in Shikai. Processing.",
    },
    {
        "anime": "Gurren Lagann",
        "quote": "Who the hell do you think this queue is?! Row row, fight the powa!",
    },
    {
        "anime": "Konosuba",
        "quote": "Aqua is 'helping' with this task. Please lower expectations.",
    },
    {
        "anime": "Code Geass",
        "quote": "Lelouch commands you: wait for this result!",
    },
    {
        "anime": "Fairy Tail",
        "quote": "The power of friendship will complete this task!",
    },
    {
        "anime": "Tokyo Ghoul",
        "quote": "This task is 1000 minus 7… 993… still counting.",
    },
    {
        "anime": "Inuyasha",
        "quote": "Sit, boy! The queue will get to you when it gets to you.",
    },
    {
        "anime": "Sailor Moon",
        "quote": "In the name of the Moon, your task will be completed! \U0001f319",
    },
    {
        "anime": "Yu-Gi-Oh!",
        "quote": "You activated my trap card: Queue Position +1.",
    },
]


def random_wait_quote() -> dict[str, str]:
    """Return a random anime waiting reference (dict with 'anime' and 'quote')."""
    return random.choice(ANIME_WAIT_QUOTES)


def random_wait_message() -> str:
    """Return a formatted one-liner ready to display."""
    entry = random_wait_quote()
    return f"*{entry['quote']}*\n— **{entry['anime']}**"
