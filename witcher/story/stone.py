"""Hearts of Stone. Original prose on the Olgierd / Gaunter spine."""

NODES = {
    "seven_cats": {
        "title": "Seven Cats Inn",
        "region": "Hearts of Stone",
        "banner": "stone",
        "rest": True,
        "hub": True,
        "unlock": {"left_vizima": True},
        "text": (
            "East of Novigrad the war thins into estates and bad decisions. A notice offers "
            "real money for a man who cannot seem to die. The innkeeper nods at a stranger by "
            "the window: fine shoes, a spoon he isn't using, a smile like a contract already "
            "signed.\n\n"
            "\"Call me Master Mirror, if you need a name,\" the stranger says. \"You won't, "
            "until you do. Olgierd von Everec owes a debt. You could collect the interest.\""
        ),
        "choices": [
            {"label": "Take the Ofieri contract. Ignore the smile.", "next": "ofieri"},
            {"label": "Ask Mirror what the interest is", "next": "mirror_talk"},
        ],
    },
    "mirror_talk": {
        "title": "A man who is mostly a bargain",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "Gaunter O'Dimm does not blink at the right times. He speaks of wishes the way a "
            "priest speaks of weather: available, local, and not his fault. \"Olgierd asked to "
            "live as he pleased, forever. People forget to define pleased.\" He slides a wooden "
            "spoon across the table. \"Keep it. Spoons are humble. They outlast swords when the "
            "story gets precious.\""
        ),
        "items": {"wooden spoon": 1},
        "set": {"met_gaunter": True},
        "choices": [
            {"label": "The Ofieri camp", "next": "ofieri"},
        ],
    },
    "ofieri": {
        "title": "Strangers with a prince's ransom",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "The Ofieri are a long way from home and short on patience. Their prince is a toad, "
            "literally, and they would like the man responsible. Olgierd von Everec drinks on a "
            "hill and kills people who come to collect. You go anyway. He fights like a man who "
            "has already attended his own funeral and found it dull.\n\n"
            "You die. That part is unambiguous. Then a ship, a shore of nothing, and Master "
            "Mirror brushing dust off a sleeve he shouldn't have."
        ),
        "set": {"died_once": True},
        "choices": [
            {"label": "Take O'Dimm's hand back", "next": "olgierd_pact", "log": "You died on Olgierd's hill. Gaunter O'Dimm charged for the return."},
        ],
    },
    "olgierd_pact": {
        "title": "A heart, a house, a brother",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "The price of breathing is three wishes Olgierd still owes, delivered by you: a "
            "brother's ghost shown one last party, a house maximized, a rose shown to a woman "
            "who no longer lives in the usual way. Olgierd grins with a scar that has its own "
            "reputation. \"Do try not to understand me. Men who understand me write poems.\"\n\n"
            "Shani is in Oxenfurt, elbow-deep in a cadaver and unimpressed by your timing. "
            "The wedding will need a plus-one who can see the dead."
        ),
        "set": {"hos_started": True},
        "choices": [
            {"label": "Oxenfurt, and Shani", "next": "wedding"},
        ],
    },
    "wedding": {
        "title": "A wedding for the dead and the rude",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "The von Everec house remembers how to throw a night. Vlodimir borrows your body "
            "because his is impractical. He drinks, boasts, and tries to steal a bride's sister's "
            "afternoon. Shani steers you through it with a doctor's contempt for nonsense and a "
            "soft spot she will deny under oath.\n\n"
            "At midnight the ghost goes, lighter. Shani looks at the empty glass and at you. "
            "\"I leave with the Oxenfurt term. I'm not a chapter you dog-ear unless you mean it.\""
        ),
        "set": {"vlod_done": True},
        "log": "Vlodimir got his night. Shani got the truth of your schedule.",
        "choices": [
            {"label": "Walk Shani home. Fade to black at the door.", "next": "shani_night", "set": {"shani_romance": True}, "romance": True},
            {"label": "Walk her home. Don't make it a ballad.", "next": "painted_gate", "set": {"shani_respected": True}},
        ],
    },
    "painted_gate": {
        "title": "Iris's painted world",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "The manor is a canvas with a lock. Inside, Iris von Everec has built a life out of "
            "pigment and spite: Olgierd as a statue, love as a room you can only cross by "
            "remembering what he spent. You collect a rose that cuts. You fight a painter's idea "
            "of a demon. You come out with the flower and the uncomfortable knowledge that "
            "Olgierd's tragedy is also his hobby."
        ),
        "set": {"iris_done": True},
        "items": {"painted rose": 1},
        "log": "Iris is at rest. The rose is a debt with thorns.",
        "choices": [
            {"label": "The temple on the lake. O'Dimm's altar.", "next": "gaunter_riddle"},
        ],
    },
    "gaunter_riddle": {
        "title": "A circle of salt and small print",
        "region": "Hearts of Stone",
        "banner": "stone",
        "text": (
            "Olgierd waits at the stone because even he can feel a bill coming due. Gaunter "
            "O'Dimm arrives without footsteps. He offers you a riddle and a circle: keep him "
            "talking until the sun hits the mark, and Olgierd's soul stays put. Fail, and you "
            "get a wish of your own, which is how this story eats people.\n\n"
            "The spoon is still in your pocket. Humble things, he said. He does love a theme."
        ),
        "choices": [
            {"label": "Answer him. Win the circle.", "next": "ending_olgierd_free", "set": {"olgierd_saved": True}, "log": "You beat Gaunter O'Dimm at his own clock."},
            {"label": "Take a wish. Let the contract complete.", "next": "ending_olgierd_taken", "set": {"gaunter_paid": True}},
        ],
    },
    "ending_olgierd_free": {
        "title": "A man with a heart again",
        "region": "Hearts of Stone",
        "banner": "ending",
        "ending": True,
        "text": (
            "The circle holds. O'Dimm's smile loses a tooth it wasn't using. He leaves the way "
            "a draft leaves, already in another inn. Olgierd touches his own chest like a man "
            "checking for a purse. \"I'll disappoint someone else now. Smaller.\" He means it "
            "as thanks.\n\n"
            "You keep the spoon. Some trophies shouldn't be silver.\n\n"
            "_Hearts of Stone: Olgierd lives. Master Mirror moves on._"
        ),
        "choices": [],
    },
    "ending_olgierd_taken": {
        "title": "Interest, collected",
        "region": "Hearts of Stone",
        "banner": "ending",
        "ending": True,
        "text": (
            "Olgierd has time to look surprised, which is new for him. Then he doesn't have "
            "time at all. O'Dimm bows, generous in victory, and offers you the wish you were "
            "too proud to phrase. You phrase something small. He gives it to you exactly, which "
            "is the punishment.\n\n"
            "_Hearts of Stone: the pact completes. You spend the wish and keep the unease._"
        ),
        "choices": [],
    },
}
