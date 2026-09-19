integer score;

default
{
    state_entry()
    {
        llSetText("Fake score: " + (string)score, <1.0, 1.0, 0.0>, 1.0);
    }
}
