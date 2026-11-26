from nazurin.config import env

PRIORITY = 10
COLLECTION = "poipiku"

with env.prefixed("POIPIKU_"):
    TOKEN: str | None = env.str("TOKEN", default=None)

    with env.prefixed("FILE_"):
        DESTINATION: str = env.str("PATH", default="Poipiku")
        FILENAME: str = env.str(
            "NAME",
            default="{id}_{index} - {user[name]}({user[id]})",
        )
