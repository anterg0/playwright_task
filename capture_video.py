import csv

from qscript import CaptureVideo_Magento

if __name__ == "__main__":
    with open("input.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            output_path = CaptureVideo_Magento(
                row["url"],
                row["company_name"],
                row["language"],
                row["country"],
                row["postcode"],
                row["city"],
                row["street"],
                row["house_no"]
            )

            if output_path:
                print(f"Success: {output_path}")
            else:
                print(f"Failed: {row['company_name']}")