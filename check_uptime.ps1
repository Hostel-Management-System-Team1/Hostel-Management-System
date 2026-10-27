
# Monitor the local Django application and log uptime checks to CSV.

$Url = "http://127.0.0.1:8000/"
$LogDir = "C:\Users\VISHNU SR\Downloads\HMS-Team1\monitoring"
$LogFile = Join-Path $LogDir "uptime.csv"

# Create the monitoring directory if it does not exist.
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Create the CSV file with a header if it does not exist.
if (-not (Test-Path $LogFile)) {
    "Timestamp,Status,HTTPStatus,ResponseTimeMs" |
        Set-Content -Path $LogFile -Encoding UTF8
}

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$Watch = [System.Diagnostics.Stopwatch]::StartNew()
$Status = "DOWN"
$HttpStatus = ""

try {
    $Request = [System.Net.HttpWebRequest]::Create($Url)
    $Request.Method = "GET"
    $Request.AllowAutoRedirect = $false
    $Request.Timeout = 10000

    try {
        $Response = $Request.GetResponse()
        $HttpStatus = [int]$Response.StatusCode
        $Response.Close()

        if ($HttpStatus -ge 200 -and $HttpStatus -lt 400) {
            $Status = "UP"
        }
    }
    catch [System.Net.WebException] {
        # HTTP error responses may still include a valid status code.
        if ($_.Exception.Response) {
            $Response = $_.Exception.Response
            $HttpStatus = [int]$Response.StatusCode
            $Response.Close()

            if ($HttpStatus -ge 200 -and $HttpStatus -lt 400) {
                $Status = "UP"
            }
        }
    }
}
catch {
    $Status = "DOWN"
}
finally {
    $Watch.Stop()
}

$Elapsed = $Watch.ElapsedMilliseconds

# Append the result to the CSV log.
"$Timestamp,$Status,$HttpStatus,$Elapsed" |
    Add-Content -Path $LogFile -Encoding UTF8

Write-Host "$Timestamp Status=$Status HTTPStatus=$HttpStatus ResponseTimeMs=$Elapsed"
