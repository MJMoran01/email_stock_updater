from email.mime.image import MIMEImage
import requests
import pandas
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.collections as collections
import datetime
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import datetime as dt
import time

STOCK = "NFLX"
NAME = "Michael"
SENDER = "Michael.Moran.bot@gmail.com"
RECIPIENT = "MichaelJMoran2001@gmail.com"
PASSWORD = ""                               # Password removed for security - this parameter must be an "app password" generated from GMAIL's 2FA
APIKEY = ""                                 # API Key for 'https://www.alphavantage.co/query?' endpoint
PARAMETERS = {
    "function": "TIME_SERIES_INTRADAY",
    "symbol": STOCK,
    "interval": "5min",
    "apikey": APIKEY,
    "datatype": "csv",
    "slice": "year1month1",
    "adjusted": False,
    "outputsize": "full",
}


def ticker_to_name(ticker: str) -> str:
    """Searches nasdaq-listed.csv to conver a stock's ticker symbol to its appropriate company name"""

    frame = pandas.read_csv("nasdaq_listed.csv")
    frame.query(f"Symbol == '{ticker}'", inplace=True)
    return frame['Name'].values[0]


def get_stock_data() -> pandas.DataFrame:
    """Sends an API request to https://www.alphavantage.co/ and returns data for the most recent trading day"""

    # Make API request and store info
    url = f'https://www.alphavantage.co/query?'
    response = requests.get(url, params=PARAMETERS)
    response.raise_for_status
    content = response.content

    # Build dataframe and store data
    with open('raw_data.csv', 'wb') as infile:
        infile.write(content)
    df = pandas.read_csv('raw_data.csv')

    # Get data for the most recent trading day. Reverse the order for plotting.
    trading_day = df['timestamp'][0].split(" ")[0]
    today_data = df[df['timestamp'].str.contains(trading_day)].iloc[::-1]
    return today_data


def format_times(today_data: dict) -> list:
    """Format timestamps for use in plot xticks"""

    formatted_times = []
    for timestamp in today_data.timestamp.values:
        # Starting Format = "YYYY-MM-DD 00:00:00"
        timestamp = timestamp.split(" ")[1]
        parts = timestamp.split(":")
        if int(parts[0]) < 12:
            parts[2] = "am"
        else:
            parts[2] = "pm"
        parts[0] = int(parts[0]) % 12
        if parts[0] == 0: parts[0] = 12
        formatted_times.append(f'{parts[0]}:{parts[1]} {parts[2]}')
    return formatted_times


def generate_plot(today_data: pandas.DataFrame) -> str:
    """ Generates a stock price plot of the passed data, returns file path of plot
        Plot is generated with 5 minute increments, and labeled with 45min increments"""

    # Pandas cannot handle multicolor line - so extract data & format it
    # Convert timestamp (x) to decimal format
    # "YYYY-MM-DD 00:00:00" -> decimal representation of hour
    x = [ (float(timestamp.split(" ")[1].split(":")[0]) + float(timestamp.split(" ")[1].split(":")[1])/60) for  timestamp in today_data.timestamp.values]
    y = today_data.open.values
    formatted_times = format_times(today_data)
    trading_day = today_data['timestamp'][0].split(" ")[0]
    filepath= f"plots/{PARAMETERS['symbol']}_Graph_{trading_day}.png"
    
    # Create nested list of line segments between each set of points to correctly color
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    lineSegments = np.concatenate([points[:-1], points[1:]], axis=1)


    # Calculate "first derivative" (A.R.O.C) for each line segment
    # map each line segment to appropriate color based on sign of first deriv
    colordict = {
        1: 'green',
        0: 'black',
        -1: 'red',
    }
    colormap = map( colordict.get , np.sign(np.diff(y))  )

    # Create and add line to axes
    line = collections.LineCollection(lineSegments, linewidths=1, colors=list(colormap))
    figure, axes = plt.subplots()
    axes.add_collection(line)

    # Configure aesthetic elemetnts (ticks, title, etc)
    # x tick labels set to every 9 increments (45min)
    axes.set_xticks(x[::9])
    axes.set_xticklabels(formatted_times[::9], rotation=90)
    axes.autoscale()
    axes.margins(0.1)
    plt.title(f"Stock price for {PARAMETERS['symbol']} on {trading_day}")
    plt.ylabel("Price in $USD")
    plt.grid()
    plt.tight_layout()
    plt.savefig(filepath)
    return filepath


def get_stats(today_data: pandas.DataFrame) -> dict:
    """Gets market open and close price (9:30am est/ 4:00pm est), max, min price, and % change for the most recent trading day"""

    trading_day = today_data['timestamp'][0].split(" ")[0]
    stats = {}
    stats['day'] = trading_day
    stats['Market Open'] = float(today_data[today_data['timestamp'] == f'{trading_day} 09:30:00'].open)
    stats['Market Close'] = float(today_data[today_data['timestamp'] == f'{trading_day} 16:00:00'].open)
    stats['max'] = float(today_data.open.max())
    stats['min'] = float(today_data.open.min())

    
    daily_return = stats["Market Close"]/stats['Market Open']
    if daily_return > 1: 
        stats['result'] = "⬆️UP⬆️"
    elif daily_return == 1: 
        stats['result'] = "Stable"
    else:
        stats['result'] = "⬇️DOWN⬇️"
    stats['change'] = round(abs(1-daily_return)*100, 3)
    return stats
    

def send_email(stats: dict, path: str) -> None:
    """Formats stock statistics and plot into an email sent from SENDER to RECIPIENT"""
    
    stock = PARAMETERS['symbol']
    day = stats.get('day')  
    companyName = ticker_to_name(stock)
    
    text = MIMEText(f"""
    Dear {NAME},

    Here is your daily update for {companyName} ({stock}): 

    {stock} was {stats['result']} {stats['change']}% on {day}

    {stock} opened at: ${stats['Market Open']:.2f} (9:30AM EST)
    {stock} closed at: ${stats['Market Close']:.2f} (4:00PM EST)
    Max price: ${stats['max']:.2f}
    Min price: ${stats['min']:.2f} 
    """)
    


    # Read png, create HTML reference for the image
    with open(path, 'rb') as infile:
        img_data = infile.read()
    plot = MIMEImage(img_data, name=path.split("/")[1])
    plotReference = MIMEText('<img src="cid:plot">', 'html')
    plot.add_header('Content-ID', '<plot>')
    
    # Format email
    message = MIMEMultipart()
    message['Subject'] = f"{stock} daily update: {day}"
    message['To'] = RECIPIENT
    message['From'] = SENDER
    message.attach(text)
    message.attach(plotReference)
    message.attach(plot)

    # Send email
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", port=465, context=ctx) as server:
        server.login(SENDER, PASSWORD)
        server.sendmail(SENDER, RECIPIENT, message.as_string())


def main():
    # Send update email every day at 8am
    while True:
        if (dt.datetime.now().hour == 8) or True:
            today_data = get_stock_data()
            stats = get_stats(today_data)
            path = generate_plot(today_data)
            send_email(stats, path)
            print(f"Email Sent to {RECIPIENT}")
        time.sleep(3600)
main()