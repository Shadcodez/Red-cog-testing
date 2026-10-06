"""Novigrad: poets, pyres, Triss, and a reason of state. Original prose."""

NODES = {
    "novigrad_gate": {
        "title": "The free city, competitively unfree",
        "region": "Novigrad",
        "banner": "novigrad",
        "rest": True,
        "hub": True,
        "unlock": {"velen_done": True},
        "text": (
            "Novigrad smells of fish, incense, and a little fear that has learned table manners. "
            "Radovid's witch hunters warm their hands at other people's lives. Temple guards "
            "practice piety at the end of a mace. Somewhere under that, Dandelion has misplaced "
            "himself again, which is almost a civic tradition.\n\n"
            "Zoltan waves from a tavern door with the relief of a dwarf who has been sober enough "
            "to worry. \"He's in a pickle. Triss is in a different pickle. The pickles are "
            "networking.\" A card deck peeks from his belt. Of course it does."
        ),
        "choices": [
            {"label": "Find Dandelion before the ballad writes itself", "next": "rosemary"},
            {"label": "Find Triss among the rats", "next": "triss_rats"},
            {"label": "Lose an hour to Gwent and call it reconnaissance", "next": "gwent_zoltan"},
            {"label": "Listen for Whoreson Junior", "next": "whoreson"},
        ],
    },
    "rosemary": {
        "title": "Rosemary and Thyme, currently theoretical",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "The cabaret is a half-built promise and a stack of bills. Priscilla — the Callonetta, "
            "if you like names that arrive with music — is keeping the doors open with charm and "
            "a knife under the ledger. Dandelion went to borrow money from men who do not lend. "
            "Whoreson Junior has him, or had him, or sold the idea of him.\n\n"
            "\"He talked about you,\" Priscilla says. \"Constantly. It was his worst quality and "
            "the reason I didn't throw the ledger at his head.\""
        ),
        "set": {"met_priscilla": True},
        "log": "Dandelion is missing. Whoreson Junior is a likely author.",
        "choices": [
            {"label": "Pay Whoreson a visit", "next": "whoreson"},
            {"label": "Triss first. Poets keep, barely.", "next": "triss_rats"},
        ],
    },
    "triss_rats": {
        "title": "The rats of Novigrad",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "Triss Merigold is hiding mages in cellars and calling it a social life. She looks "
            "tired in a way sleep doesn't fix. When she sees you, some of the tiredness decides "
            "to sit down.\n\n"
            "\"Ciri was here,\" she says, immediately, because she has always been the one who "
            "leads with the point. \"She found Dandelion. Then the hunters got close and she ran "
            "again. I can get you to people who saw her. I need a witcher who can walk into a "
            "masquerade and not start a proverb.\""
        ),
        "set": {"met_triss": True},
        "choices": [
            {"label": "Agree to the masquerade", "next": "masquerade", "log": "Triss needs a partner who can dance and stab, preferably in that order."},
            {"label": "Ask her plainly if she is all right", "next": "triss_quiet"},
        ],
    },
    "triss_quiet": {
        "title": "A question she didn't budget for",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "Triss studies a crack in the cellar wall as if it might answer for her. \"I'm "
            "smuggling children with talent out of a city that wants them as candles. So. No. "
            "But I am busy, which is the acceptable version.\" She bumps your shoulder with hers, "
            "old habit, dangerous habit. \"Masquerade. Then we can be people, if there's time "
            "left over from being useful.\""
        ),
        "choices": [
            {"label": "The masquerade", "next": "masquerade"},
        ],
    },
    "masquerade": {
        "title": "Masks, and the men who rent them",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "The Vegelbud ball is silk over a counting house. You dance because Triss asks, and "
            "because a witcher who will not dance is just a weapon with opinions. She laughs once "
            "into your collar when you miss a step. \"Books never mention this part. The great "
            "destiny of Geralt of Rivia, trodding on a sorceress.\"\n\n"
            "Between the music and a crossbow bolt you extract a ledger: mages sold, routes "
            "bought, Whoreson taking a cut. Ciri's name is not in it. Dandelion's is, in the "
            "margin, next to a sum that would embarrass a king."
        ),
        "set": {"did_masquerade": True},
        "items": {"crowns": 40, "stolen ledger": 1},
        "choices": [
            {"label": "Use the ledger on Whoreson", "next": "whoreson"},
            {"label": "Walk Triss home first", "next": "triss_door"},
        ],
    },
    "triss_door": {
        "title": "A doorway with a second meaning",
        "region": "Novigrad",
        "banner": "romance",
        "text": (
            "The safehouse stairs smell of damp wool and cinnamon, which is Triss's whole "
            "theology. She stops with her hand on the latch. Hunters will move tomorrow. Ships "
            "leave for Kovir if she can fill them. She could also not get on one.\n\n"
            "\"If you ask me to stay,\" she says, \"I will hear it. The door can close. The "
            "rest of the evening does not need an audience. If you don't ask, I will still help "
            "you. I'm not a contract, Geralt. I'm a woman who has already made this mistake "
            "once and remembers why it didn't feel like one.\""
        ),
        "choices": [
            {"label": "Ask her to stay. Fade to black at the lighthouse.", "next": "triss_dock", "set": {"triss_romance": True}, "romance": True},
            {"label": "Help the ship. Don't ask her to stay.", "next": "whoreson", "set": {"triss_left": True}, "log": "Triss will sail. You did not ask her to do otherwise."},
        ],
    },
    "whoreson": {
        "title": "Junior, a professional disappointment",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "Whoreson Junior has redecorated in blonde and bad ideas. Dandelion is alive out of "
            "narrative stubbornness, tied to a chair and already composing the version where he "
            "was never afraid. Whoreson talks about Ciri as merchandise. That shortens the talk.\n\n"
            "After, the poet coughs, grins, and has the gall to look pleased. \"I knew you'd "
            "come. I told them. They charged me extra for the confidence.\" He knows a doppler "
            "who wore Ciri's face, and a beggar-king who sells the city's underside by the pound."
        ),
        "set": {"saved_dandelion": True},
        "log": "Dandelion lives. Whoreson Junior does not improve the city by leaving it.",
        "choices": [
            {"label": "Find the doppler", "next": "dudu"},
            {"label": "Straight to the King of Beggars", "next": "beggars"},
        ],
    },
    "dudu": {
        "title": "A face you almost trust",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "Dudu wears a clerk until he decides to wear honesty. He sheltered Ciri for a night "
            "because she asked like someone who had run out of allies and refused to run out of "
            "manners. She spoke of an elf on Skellige, and of a curse she put on a man who tried "
            "to sell her — horns, misery, a joke cruel enough to be elven.\n\n"
            "\"Uma,\" Dudu says, tasting it. \"Ugly. Also anagrams, if you like puzzles more "
            "than sleep. She went to the isles after. Your sorceress was already on a ship.\""
        ),
        "set": {"uma_confirmed": True},
        "log": "Ciri cursed a trafficker into Uma and ran for Skellige.",
        "choices": [
            {"label": "The King of Beggars still has a price list", "next": "beggars"},
            {"label": "Enough city. Skellige.", "next": "skellige_dock"},
        ],
    },
    "beggars": {
        "title": "Charity, professionally armed",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "The King of Beggars receives you on a throne of crates. Dijkstra is there too, "
            "larger than the room's intentions, cane across his knee, mind already three murders "
            "ahead. Between them they offer a plan so patriotic it needs washing: Radovid dies, "
            "temple fires cool, and the North gets to lose the war more slowly.\n\n"
            "Roche and Ves would do the knife-work. Dijkstra would do the after. You are invited "
            "to be the consequence."
        ),
        "set": {"heard_plot": True},
        "choices": [
            {"label": "Hear Dijkstra out", "next": "radovid_plot"},
            {"label": "Stay out of kings. Find Yen.", "next": "skellige_dock", "set": {"skipped_plot": True}},
        ],
    },
    "radovid_plot": {
        "title": "A reason of state",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "The bridge is a stage and Radovid is a madman who has read too much of his own "
            "poster. It goes wrong in the specific way of plans that involve Dijkstra. The king "
            "dies. That part works. Then Dijkstra's men step out of the fog with the calm of "
            "people who were always the second act, and Roche looks at you because somebody has "
            "to choose which North gets to see morning.\n\n"
            "Dijkstra's cane taps once. \"Temeria is a feeling, witcher. I am a government.\""
        ),
        "choices": [
            {"label": "Stand with Roche and Ves", "next": "reason_roche", "set": {"roche_lives": True, "dijkstra_dead": True}, "log": "Radovid is dead. Roche kept Temeria's ghost. Dijkstra did not keep the bridge."},
            {"label": "Step aside. Let Dijkstra finish it.", "next": "reason_dijkstra", "set": {"dijkstra_wins": True, "roche_dead": True}, "log": "You let Dijkstra take the North. Roche did not walk off that bridge."},
            {"label": "Walk away before the cane comes up", "next": "reason_walk", "set": {"plot_abandoned": True}},
        ],
    },
    "reason_roche": {
        "title": "Temeria, in two people and a grudge",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "It is ugly and quick. Dijkstra falls like a scheme with the floor removed. Roche "
            "doesn't thank you. Ves does, with a look, which is more. The witch hunters will "
            "scatter without their mad king. Mages may yet die of other causes. They usually do.\n\n"
            "Ciri is not in this city. The isles are calling in Yennefer's handwriting, even "
            "when the letter is only a rumor."
        ),
        "choices": [
            {"label": "Take a ship", "next": "skellige_dock"},
            {"label": "If Triss has not sailed, find the dock", "next": "triss_dock", "requires": {"triss_romance": True}},
        ],
    },
    "reason_dijkstra": {
        "title": "A colder peace",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "You look at the water until the sounds stop. Dijkstra nods as if you have signed "
            "something. \"Sensible. I'll mention you only if it helps.\" Roche is a shape on "
            "the planks you decide not to memorize. The North will have bread and spies. It "
            "will not have the men who still said Temeria out loud.\n\n"
            "Your job is still a girl. The isles, before this victory learns your name."
        ),
        "choices": [
            {"label": "Skellige", "next": "skellige_dock"},
        ],
    },
    "reason_walk": {
        "title": "Not your war, again",
        "region": "Novigrad",
        "banner": "novigrad",
        "text": (
            "You leave the bridge to professionals. By morning the story has three versions and "
            "you are in none of them, which is a kind of payment. Triss's rats scatter anyway. "
            "Dandelion writes a ballad with the politics sanded off.\n\n"
            "Yennefer, the sailors say, has already insulted a jarl. Time to go be insulted in person."
        ),
        "choices": [
            {"label": "The isles", "next": "skellige_dock"},
        ],
    },
}
