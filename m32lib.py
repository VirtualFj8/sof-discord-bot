import struct
import sys

"""
USAGE:

with open(filename,'rb') as m32file:
	data = m32file.read()
mipheader = m32lib.MipHeader(filename,data)
mipheader.dump()
w = int(mipheader.width.read()[0])
h = int(mipheader.height.read()[0])
mipheader.imgdata()
"""

MIPLEVELS = 16


def getTypeSize(tipe):

	if tipe == 'int':
		o=4
	elif tipe == 'uint':
		o=4
	elif tipe == 'string':
		o=0
	elif tipe == 'float':
		o=4
	else:
		o=0
	return o



class Field:
	@staticmethod
	def memToString(mem,tipe,size=128):
		mem = mem.tobytes()
		if tipe == 'int':
			outstring = str(struct.unpack('<i',mem)[0])
		elif tipe == 'uint':
			outstring = str(struct.unpack('<I',mem)[0])
		elif tipe == 'string':
			outstring = str(struct.unpack( str(size) + 's',mem )[0])
			nil = outstring.find('\0')
			if nil >= 0:
				outstring = outstring[:nil]
		elif tipe == 'float':

			outstring = str(struct.unpack('<f',mem)[0])
		# print type(outstring)
		return outstring

	def __init__(self,name,size,tipe,view=None):
		self.name = name
		self.size = size
		self.tipe = tipe
		self.memview = None if view is None else view[:size]


	def writeBasic(self,mem,tipe,data):
		"""
		mem = memview into bytearray
		struct.pack_into(format, buffer, offset, v1, v2, ...)
		"""
		if tipe == 'int':
			struct.pack_into('<i',mem,0, data)
		elif tipe == 'uint':
			struct.pack_into('<I',mem,0,data)
		elif tipe == 'string':
			encoded_data = data.encode()
			mem[0:len(encoded_data)] = encoded_data
			mem[len(encoded_data)] = 0  # Null-terminate the string
		elif tipe == 'float':
			struct.pack_into('<f',mem,0,data)

	def write(self,val,list_offset=0):
		if self.memview is None:
			return
		tipe = self.tipe
		if tipe.find('list_') == 0:
			tipe = self.tipe[5:]
			ts = getTypeSize(tipe)
			# for x in range(0,self.size,ts):
			# 	self.writeBasic(tipe)
			# Write only to the list_offset.
			# print(f"TS is {ts} tipe is {tipe} val is {val} listoffset is {list_offset}")
			self.writeBasic(self.memview[list_offset*ts:list_offset*ts+ts],tipe,val)
		else:
			self.writeBasic(self.memview,tipe,val)


	def read(self):
		"""
			if its a list, return a list, instead.
		"""
		if self.tipe.find('list_') == 0:
			return self.toList()
		return self.toString()

	def toString(self):
		return Field.memToString(self.memview,self.tipe)

	def toList(self):
		tipe = self.tipe[5:]
		ts = getTypeSize(tipe)
		return [Field.memToString(self.memview[x:x+ts],tipe) for x in range(0,self.size,ts)]


class MipHeader:
	
	fields = [
				Field('version',4,'int'),
				Field('name',128,'string'),
				Field('altname',128,'string'),
				Field('animname',128,'string'),
				Field('damagename',128,'string'),
				Field('width',MIPLEVELS*4,'list_uint'),
				Field('height',MIPLEVELS*4,'list_uint'),
				Field('offsets',MIPLEVELS*4,'list_uint'),
				Field('flags',4,'int'),
				Field('contents',4,'int'),
				Field('value',4,'int'),
				Field('scale_x',4,'float'),
				Field('scale_y',4,'float'),
				Field('mip_scale',4,'int'),
				Field('dt_name',128,'string'),
				Field('dt_scale_x',4,'float'),
				Field('dt_scale_y',4,'float'),
				Field('dt_u',4,'float'),
				Field('dt_v',4,'float'),
				Field('dt_alpha',4,'float'),
				Field('dt_src_blend_mode',4,'int'),
				Field('dt_dst_blend_mode',4,'int'),
				Field('flags2',4,'int'),
				Field('damage_health',4,'float'),
				Field('unused',18*4,'list_int'),

	]
	def __init__(self,filename='',infileData=None,dictIn=None):
		self.filename = filename
		if infileData is not None:
			# print("Hmm")

			self.file = bytearray(infileData)

			mview = memoryview(self.file)
			# apply memoryview segment for each variable
			for field in MipHeader.fields:
				# store this field type in this class instance with memview of data
				f = Field(field.name,field.size,field.tipe,mview[:])
				setattr(self,field.name,f)
				# jump forward
				mview = mview[field.size:]

		elif dictIn is not None:
			# write instead of read, creates defaults.
			self.file = bytearray(968)
			mview = memoryview(self.file)
			for field in MipHeader.fields:
				f = Field(field.name,field.size,field.tipe,mview[:])
				if field.name in dictIn:
					if f.name == "width" or f.name == "height" or f.name == "offsets":
						for x in range(0,MIPLEVELS):
							f.write(dictIn[field.name][x],x);
					else:
						f.write(dictIn[field.name])

				setattr(self,field.name,f)
				mview = mview[field.size:]
		else:
			print("Error : please pass a file to this function")
			sys.exit(1)

	def header(self):
		return memoryview(self.file)[:len(self)]

	def imgdata(self):
		# len(self) = 968 *trick*
		return memoryview(self.file)[ len(self)  :  len(self)+int(self.width.read()[0]) * int(self.height.read()[0]) *4 ]

	def dump(self):
		print("dumping contents of " + self.filename)

		startview = memoryview(self.file)
		for field in MipHeader.fields:
			if field.tipe.find('list_') == 0:
				# list of what... type?
				tipe = field.tipe[5:]
				ts = getTypeSize(tipe)
				if ts == 0 :
					print("Error : unsupported list")
					sys.exit(1)
				
				# increment x by the type size.
				for x in range(0,field.size,ts):
					# for every element in list
					u = len(field.name) + len(str(x)) + 2
					y = 30 - u
					if y < 0:
						y = 0
					field_str = Field.memToString(startview[:4],tipe)
					print(field.name + "[" + str(x) + "]" + " is" + y*' ' + " : " + field_str)
					startview = startview[ts:]
			else:
				u = len(field.name)
				y = 30 - u
				if y < 0:
					y = 0			
				fld = getattr(self,field.name)
				print (field.name + " is" + y*' ' + " : " + fld.read())
				startview = startview[fld.size:]

	def __len__(self):
		return 968