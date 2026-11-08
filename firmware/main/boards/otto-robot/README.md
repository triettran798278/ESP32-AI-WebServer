<p align="center">
  <img width="80%" align="center" src="../../../docs/V1/otto-robot.png"alt="logo">
</p>
  <h1 align="center">
  ottoRobot
</h1>

## 

otto , .  ESP32  otto , ai. 

- <a href="www.ottodiy.tech" target="_blank" title="otto"></a>

## 
- <a href="https://oshwhub.com/txp666/ottorobot" target="_blank" title=""></a>

## configrole: 

> ****: 
> Otto,  (, , , ) , . 
> 
> ****: 
> - ****: (), (), 
> - ****: , , , , 
> - ****: , ,  (config)
> 
> ****: 
> - ,  (send) 
> - , 
> - , : 
>   - 
>   - 
>   - 
>   - 
>   - 
>   - 

## 

otto , , , , . 

### param
- ****: speed = 1200-1500 ()
- ****: speed = 900-1200 (use)  
- ****: speed = 500-800 ()
- ****: amount = 10-30 ()
- ****: amount = 30-60 ()
- ****: amount = 60-120 ()

### 

| MCPtoolname         | description             | param                                              |
|-------------------|-----------------|---------------------------------------------------|
| self.otto.walk_forward |            | **steps**: (1-100, default3)<br>**speed**: (500-1500, , default1000)<br>**direction**: (-1=, 1=, default1)<br>**arm_swing**: (0-170, default50) |
| self.otto.turn_left |             | **steps**: (1-100, default3)<br>**speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, default1)<br>**arm_swing**: (0-170, default50) |
| self.otto.jump    |             | **steps**: (1-100, default1)<br>**speed**: (500-1500, , default1000) |
| self.otto.swing   | Sway left and right        | **steps**: (1-100, default3)<br>**speed**: (500-1500, , default1000)<br>**amount**: (0-170, default30) |
| self.otto.moonwalk |          | **steps**: (1-100, default3)<br>**speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, default1)<br>**amount**: (0-170, default25) |
| self.otto.bend    |         | **steps**: (1-100, default1)<br>**speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, default1) |
| self.otto.shake_leg |           | **steps**: (1-100, default1)<br>**speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, default1) |
| self.otto.updown  |         | **steps**: (1-100, default3)<br>**speed**: (500-1500, , default1000)<br>**amount**: (0-170, default20) |
| self.otto.hands_up |  *         | **speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, 0=, default1) |
| self.otto.hands_down |  *       | **speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, 0=, default1) |
| self.otto.hand_wave |  *        | **speed**: (500-1500, , default1000)<br>**direction**: (1=, -1=, 0=, default1) |

****:  * config. 

### tool

| MCPtoolname         | description             | return                                              |
|-------------------|-----------------|---------------------------------------------------|
| self.otto.stop    | stop        | stop |
| self.otto.get_status | getstatus | return "moving"  "idle" |
| self.battery.get_level | getstatus  | returnbatterychargingstatusJSON |

### param

1. **steps**: /, time
2. **speed**: , 500-1500, ****
3. **direction**: param
   - : 1=/, -1=/
   - : 1=, -1=, 0=
4. **amount/arm_swing**: , 0-170
   - 0 () 
   - 

### 
- , (home), 
- paramdefault, param
- , 
- support, 

### MCPtoolcall
```json
// 3
{"name": "self.otto.walk_forward", "arguments": {}}

// 5, 
{"name": "self.otto.walk_forward", "arguments": {"steps": 5, "speed": 800}}

// 2,   
{"name": "self.otto.turn_left", "arguments": {"steps": 2, "arm_swing": 100}}

// , 
{"name": "self.otto.swing", "arguments": {"steps": 5, "amount": 50}}

{"name": "self.otto.hand_wave", "arguments": {"direction": 1}}

// stop
{"name": "self.otto.stop", "arguments": {}}
```

### voice
- "" / "5" / ""
- "" / "" / ""  
- "" / ""
- "" / ""
- "" / ""
- "" / "" / ""
- "stop" / ""

****: create, voice. "stop"voiceOtto. 

