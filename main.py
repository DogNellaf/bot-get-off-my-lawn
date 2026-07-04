import argparse

from bot.bot import LawnBot
from bot.config import Config
from bot.logger import write_line


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug",
        action="store_true",
        help="раз в секунду печатать оценки угроз по дорожкам",
    )
    args = parser.parse_args()

    write_line("[GetOffMyLawnBot]")
    config = Config.load_or_init()
    bot = LawnBot(config, debug=args.debug)
    bot.run_forever()


if __name__ == "__main__":
    main()
