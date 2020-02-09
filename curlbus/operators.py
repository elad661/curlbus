""" This file contains some hard-coded maps with data about transit operators,
to compensate for some missing bits in the MoT dataset """
import os.path

operators = {'rail': 2,
             'egged': 3,
             'egged_tavura': 4,
             'dan': 5,
             'unbs': 6,
             'ntt': 7,
             'gbtours': 8,
             'nativ_express': 14,
             'metropoline': 15,
             'superbus': 16,
             'kavim': 18,
             'carmelit': 20,
             'citypass': 21,
             'galim': 23,
             'golan': 24,
             'afikim': 25,
             'metronit': 30,
             'dan_south': 31,
             'dan_beersheba': 32,
             'cable_express': 33,  # ??????
             # East Jerusalem operators - not a lot of info online, so I might
             # be committing horrible spelling mistakes here
             'jlm_ramalla': 42,
             'jlm_abu_tor': 44,
             'jlm_alwst': 45,
             'jlm_mountolives': 47,
             'jlm_isawiya': 49,
             'jlm_south': 50,
             'jlm_sur_baher': 51,
             # Sherut taxis
             'sherut_shai_li': 92,
             'sherut_maya': 93,
             'sherut_shiran_nessiot': 94,
             'sherut_yahlom': 95,
             'sherut_galim': 96,
             'sherut_hai': 97,
             'sherut_4_5': 98,
             'sherut_hadar_lod': 130,
            }
"""mapping URL slugs for operator IDs. This has to be done because the original
name in the GTFS agency.txt is in Hebrew, and that wouldn't be nice in a URL"""

operators_by_id = {v: k for k, v in operators.items()}

operator_names = {2: "Israel Railways",
                  3: "Egged",
                  4: "Egged Taavura",
                  5: "Dan",
                  6: "Nazareth UNBS",
                  7: "Nazareth Transport & Tourism",
                  8: "GB Tours",
                  14: "Nativ Express",
                  15: "Metropoline",
                  16: "Superbus",
                  18: "Kavim",
                  20: "Carmelit",
                  21: "Citypass",
                  23: "Galim",
                  24: "Golan Regional Council",
                  25: "Afikim",
                  30: "Metronit (Dan North)",
                  31: "Dan South",
                  32: "Dan Beersheba",
                  33: "Cable Express (?)",  # ????
                  # Not sure about the spelling here, I just guessed
                  42: "Jerusalem - Ramalla",
                  44: "Jerusalem - Abu Tor",
                  45: "Jerusalem - Alwst",
                  47: "Jerusalem - Mount Olives",
                  49: "Jerusalem - Isawiya and Shuafat",
                  50: "Jerusalem - South",
                  51: "Jerusalem - Sur Baher",
                  # Sherut taxis:
                  92: "Sherut: Shai Li",
                  93: "Sherut: Maya Yitzhak Sade",
                  94: "Sherut: Shiran Nessi'ot",
                  95: "Sherut: Yahalom Transportation",
                  96: "Sherut: Galim",
                  97: "Sherut: Hai",
                  98: "Sherut: Rav-Kavit 4-5",
                  130: "Sherut: Hadar-Lod",
                  }
""" Translating operator names to English, as this is missing from the
official translation table """

_logos_dir = os.path.join(os.path.dirname(__file__), "operator_logos")
operator_logos = {2: os.path.join(_logos_dir, "rail.txt"),
                  3: os.path.join(_logos_dir, "egged.txt"),
                  5: os.path.join(_logos_dir, "dan.txt"),
                  15: os.path.join(_logos_dir, "metropoline.txt"),
                  18: os.path.join(_logos_dir, "kavim.txt"),
                  20: os.path.join(_logos_dir, "carmelit.txt"),
                  21: os.path.join(_logos_dir, "citypass.txt"),
                  25: os.path.join(_logos_dir, "afikim.txt"),
                  30: os.path.join(_logos_dir, "metronit.txt")}
