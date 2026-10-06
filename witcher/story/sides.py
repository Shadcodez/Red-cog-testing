"""Major side roads: contracts, Gwent, Fyke, a book-fire. Original prose."""

NODES = {
    "devil_well": {
        "title": "The devil by the well",
        "region": "White Orchard",
        "banner": "orchard",
        "text": (
            "The well smells of a wedding that soured. By day she is a heat-shimmer over the "
            "yard. By noon she is a bride with a neck the wrong length, hunting the living "
            "because the living watched. A noonwraith wants a proper grave more than she wants "
            "your head, but she will take the head on the way.\n\n"
            "You burn the letter that married her off, salt the bones, and put her down when "
            "she rises anyway. The ealdorman pays. He does not attend the second burial."
        ),
        "set": {"well_done": True},
        "items": {"crowns": 60},
        "log": "The noonwraith at the well is at rest.",
        "choices": [
            {"label": "Vizima is still waiting", "next": "vizima_gate", "requires": {"not:left_vizima": True}},
            {"label": "Back to the inn", "next": "crossroads"},
        ],
    },
    "gwent_orchard": {
        "title": "A deck and a liar",
        "region": "White Orchard",
        "banner": "inn",
        "text": (
            "The merchant plays like a man who once won a cow and has been chasing the feeling. "
            "You lose a hand on purpose, then don't. He forks over a spy card and a story about "
            "Nilfgaardian decoys, which you already knew, plus four crowns, which you didn't.\n\n"
            "\"Your poet friend plays worse,\" he says. \"Tell him I said it. He'll write a "
            "song and I'll charge admission.\""
        ),
        "items": {"crowns": 4, "gwent spy": 1},
        "set": {"gwent_started": True},
        "choices": [
            {"label": "Back to the real hunt", "next": "griffin_rumor"},
        ],
    },
    "gwent_zoltan": {
        "title": "Zoltan's office hours",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "Zoltan deals and talks at the same time, a dwarf's idea of efficiency. \"Dandelion's "
            "in a hole. Triss is in a different hole. You're the shovel, as usual.\" He slaps "
            "down a hero card you actually want. \"Don't say I never paid you. Also don't tell "
            "the wife I bet the good mug.\"\n\n"
            "The game is a rest. The city is not."
        ),
        "items": {"gwent hero": 1, "crowns": 10},
        "choices": [
            {"label": "Back to the gates", "next": "novigrad_gate"},
        ],
    },
    "fyke_dock": {
        "title": "Fyke Isle, mice and a tower",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "A fisherman will row you if you sit still and don't mention the plague. The tower "
            "is a black thumb. Graham's ghost, or his guilt, still walks the causeway. Anabelle "
            "is in the water, a pox-ridden girl who wants a promise carried to her father: that "
            "he comes, that he looks, that he doesn't send a servant.\n\n"
            "Fathers in this country have a poor record."
        ),
        "choices": [
            {"label": "Carry her bones to the father", "next": "fyke_father"},
            {"label": "Tell Graham the truth and let the tower burn its own lesson", "next": "fyke_end", "set": {"fyke_done": True}},
        ],
    },
    "fyke_father": {
        "title": "A father at the door",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "He will not look in the sack. You make him. The story goes the way these stories "
            "go when a man loved his rank more than his child: shouting, a curse, a wraith that "
            "was a daughter. You put her down in the yard she grew up in. Graham, if he is still "
            "listening, stops walking the causeway.\n\n"
            "The fisherman rows you back for free. Even he has limits."
        ),
        "set": {"fyke_done": True, "anabelle_ended": True},
        "items": {"crowns": 30},
        "log": "Fyke Isle is quieter. It did not become kinder.",
        "choices": [
            {"label": "Return to the Crossroads", "next": "velen_inn"},
            {"label": "Keira's light is still on", "next": "keira_tower", "requires": {"not:met_keira": True}},
        ],
    },
    "fyke_end": {
        "title": "A causeway left to itself",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "You tell Graham his daughter waited. He already knew. Knowing was the haunting. "
            "You leave the isle to the mice and the moral. Some contracts are just witnessing."
        ),
        "choices": [
            {"label": "The inn", "next": "velen_inn"},
        ],
    },
    "shrieker_board": {
        "title": "A contract with too many teeth",
        "region": "Velen",
        "banner": "velen",
        "text": (
            "The notice says a demon. The tracks say a fiend, half-blind and mad with pain from "
            "a broken horn. Peasants have been feeding it rumors. You track it to a ravine, "
            "wait until it charges the wrong echo, and put silver where the skull already gave "
            "up.\n\n"
            "The ealdorman pays in coin and cabbage. You accept both. Pride is lighter when fried."
        ),
        "set": {"shrieker_done": True},
        "items": {"crowns": 70, "fiend eye": 1},
        "log": "A fiend contract in Velen, done without a speech.",
        "choices": [
            {"label": "Crow's Perch is still the real job", "next": "baron_hall", "requires": {"not:met_baron": True}},
            {"label": "Back to the inn", "next": "velen_inn"},
        ],
    },
    "cat_school": {
        "title": "Where the cat and wolf share a road",
        "region": "Novigrad outskirts",
        "banner": "velen",
        "text": (
            "A Cat-school witcher is cutting through a village that may have deserved a trial "
            "and did not get one. He knows your name. He does not care about your code, which "
            "he calls a story Wolves tell so they can sleep. The fight is short and miserable. "
            "After, a child who hid in a cellar asks if all witchers are like that.\n\n"
            "You say no. You are not entirely sure the answer survives contact with Lambert."
        ),
        "set": {"cat_done": True},
        "items": {"cat medallion": 1},
        "log": "A Cat-school contract ended in the ditch it deserved.",
        "choices": [
            {"label": "Novigrad gate", "next": "novigrad_gate", "requires": {"velen_done": True}},
            {"label": "Velen inn", "next": "velen_inn", "requires": {"left_vizima": True}},
            {"label": "Back to a fire, if the roads argue", "next": "book_fire"},
        ],
    },
    "book_fire": {
        "title": "A fire, a book, no destiny in the room",
        "region": "On the road",
        "banner": "inn",
        "rest": True,
        "text": (
            "Some nights the campaign lets you sit. You read a dog-eared thing about the Law of "
            "Surprise — a child promised because a man saved a stranger and asked for what the "
            "stranger did not yet know he had. It ends badly, which is how you know it's accurate. "
            "The innkeeper asks if witchers dream. You say yes. You do not say of what.\n\n"
            "Roach steals an apple. The world, briefly, is only that."
        ),
        "choices": [
            {"label": "White Orchard", "next": "crossroads"},
            {"label": "Velen, if the emperor already paid you", "next": "velen_inn", "requires": {"left_vizima": True}},
            {"label": "Novigrad", "next": "novigrad_gate", "requires": {"velen_done": True}},
            {"label": "Skellige", "next": "skellige_dock", "requires": {"velen_done": True}},
            {"label": "The Ofieri road", "next": "seven_cats", "requires": {"left_vizima": True}},
            {"label": "Toussaint", "next": "beauclair", "requires": {"left_vizima": True}},
            {"label": "The wolf keep", "next": "kaer_morhen", "requires": {"uma_in_hand": True}},
        ],
    },
}
